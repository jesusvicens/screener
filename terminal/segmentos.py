"""Ventas (y resultado) por segmento, producto y geografía, sacados del XBRL «dimensional» de los 10-K.

La API companyfacts de la SEC no incluye estos desgloses: se leen del fichero XBRL de cada 10-K (*_htm.xml)
y de sus etiquetas (*_lab.xml) para tener los nombres tal como los publica la empresa.
"""
from __future__ import annotations

import gzip
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd

from . import sec

REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
       "SalesRevenueNet", "RevenuesNetOfInterestExpense"]
OPI = ["OperatingIncomeLoss", "SegmentReportingInformationOperatingIncomeLoss"]
AXES = {"StatementBusinessSegmentsAxis": "Segmento", "ProductOrServiceAxis": "Producto o servicio",
        "StatementGeographicalAxis": "Geografía", "ConsolidationItemsAxis": None}


def _clean_label(x: str) -> str:
    """«International Segment» y «International» son el mismo segmento (cambios de etiqueta entre años)."""
    return re.sub(r"\s+(Segment|Segmento|Reportable Segment|Operating Segment)$", "", str(x or "")).strip()


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _pretty(member: str) -> str:
    m = member.split(":")[-1]
    m = re.sub(r"(Member|Segment)$", "", m)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", m).strip()


def _labels(url: str) -> dict[str, str]:
    """Etiqueta «terse/label» de cada miembro (adbe_DigitalMediaMember → «Digital Media»)."""
    try:
        root = ET.fromstring(sec._get(url).content)
    except Exception:  # noqa: BLE001
        return {}
    xlink = "{http://www.w3.org/1999/xlink}"
    loc, arcs, labs = {}, [], {}
    for el in root.iter():
        t = _local(el.tag)
        if t == "loc":
            loc[el.get(xlink + "label")] = el.get(xlink + "href", "").split("#")[-1]
        elif t == "labelArc":
            arcs.append((el.get(xlink + "from"), el.get(xlink + "to")))
        elif t == "label":
            role = el.get(xlink + "role", "")
            if role.endswith("/label") or role.endswith("terseLabel"):
                labs.setdefault(el.get(xlink + "label"), []).append((role.endswith("terseLabel"), (el.text or "").strip()))
    out = {}
    for f, t in arcs:
        concept = loc.get(f)
        if concept and t in labs:
            best = sorted(labs[t], key=lambda x: not x[0])[0][1]
            out[concept.replace("_", ":", 1)] = re.sub(r"\s*\[Member\]$", "", best)
    return out


def _parse(instance: bytes, labels: dict, quarterly: bool = False) -> list[dict]:
    root = ET.fromstring(instance)
    ctx = {}
    for c in root.iter():
        if _local(c.tag) != "context":
            continue
        mem = [(m.get("dimension"), (m.text or "").strip()) for m in c.iter() if _local(m.tag) == "explicitMember"]
        typed = [m for m in c.iter() if _local(m.tag) == "typedMember"]
        st_ = en = None
        for p in c.iter():
            if _local(p.tag) == "startDate":
                st_ = p.text
            elif _local(p.tag) == "endDate":
                en = p.text
        if not st_ or not en or typed:
            continue
        ctx[c.get("id")] = (st_, en, mem)
    rows = []
    for el in root:
        name = _local(el.tag)
        kind = "Ventas" if name in REV else ("Resultado operativo" if name in OPI else None)
        if not kind or el.get("contextRef") not in ctx:
            continue
        st_, en, mem = ctx[el.get("contextRef")]
        days = (date.fromisoformat(en) - date.fromisoformat(st_)).days
        if quarterly:
            if not (80 < days < 100 or 350 < days < 380 or 170 < days < 190 or 260 < days < 285):
                continue
        elif not 350 < days < 380:
            continue
        dims = [(d.split(":")[-1], m) for d, m in mem]
        main = [(d, m) for d, m in dims if d in AXES and AXES[d]]
        if {d for d, _m in main} == {"StatementBusinessSegmentsAxis", "StatementGeographicalAxis"}:
            main = [(d, m) for d, m in main if d == "StatementBusinessSegmentsAxis"]  # segmento que es a la vez geografía
        other = [(d, m) for d, m in dims if d not in AXES]
        if len(main) != 1 or other or any(d == "ConsolidationItemsAxis" and "Operating" not in m for d, m in dims):
            continue
        d, m = main[0]
        try:
            v = float(el.text)
        except (TypeError, ValueError):
            continue
        rows.append({"Tipo": AXES[d], "Dato": kind, "Id": m, "Miembro": labels.get(m) or _pretty(m), "Año": int(en[:4]), "Fin": en,
                     "Inicio": st_, "Días": days,
                     "Valor": v / 1e6, "Etiqueta": name})
    return rows


def breakdown(cik: int, n_filings: int = 3, max_age_h: float = 24 * 7) -> pd.DataFrame:
    """Desglose de los últimos `n_filings` 10-K (cada uno trae 3 años): columnas Tipo, Dato, Miembro, Año, Valor (M$)."""
    path = sec.CACHE_DIR / f"segmentos_{int(cik):010d}.json.gz"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_h * 3600:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return pd.DataFrame(json.load(f))
    s = sec.submissions(int(cik))
    r = s.get("filings", {}).get("recent", {})
    accs = [r["accessionNumber"][i] for i, f in enumerate(r.get("form", [])) if f in ("10-K", "10-K/A")][:n_filings]
    rows = []
    for k, acc in enumerate(accs):
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        try:
            items = [x["name"] for x in sec._get(base + "index.json").json()["directory"]["item"]]
            inst = [x for x in items if x.endswith("_htm.xml")] or [x for x in items if re.search(r"\d{8}\.xml$", x)]
            lab = [x for x in items if x.endswith("_lab.xml")]
            if not inst:
                continue
            labels = _labels(base + lab[0]) if lab else {}
            for x in _parse(sec._get(base + inst[0]).content, labels):
                x["Prioridad"] = k  # el 10-K más reciente manda (por si reclasifican)
                rows.append(x)
        except Exception:  # noqa: BLE001
            continue
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Prioridad").drop_duplicates(["Tipo", "Dato", "Id", "Año"])
        # el nombre más reciente para cada miembro (las empresas retocan las etiquetas de un año a otro)
        df["Miembro"] = df["Id"].map(df.drop_duplicates("Id").set_index("Id")["Miembro"]).map(_clean_label)
        df = df.drop_duplicates(["Tipo", "Dato", "Miembro", "Año"]).drop(columns="Prioridad")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(df.to_dict("records"), f)
    return df


def pivot(df: pd.DataFrame, tipo: str, dato: str = "Ventas") -> pd.DataFrame:
    d = df[(df["Tipo"] == tipo) & (df["Dato"] == dato)]
    if d.empty:
        return pd.DataFrame()
    p = d.pivot_table(index="Miembro", columns="Año", values="Valor", aggfunc="first").sort_index(axis=1)
    last = p.columns[-1]
    return p.sort_values(last, ascending=False)


def quarterly(cik: int, n_filings: int = 14, max_age_h: float = 24 * 7) -> pd.DataFrame:
    """Desglose por trimestre (10-Q y 10-K): columnas Tipo, Dato, Miembro, Fin, Valor (M$).

    Los 10-Q traen el trimestre (3 meses); el 4.º trimestre se calcula como el año (10-K) menos los 9 meses del 10-Q anterior.
    """
    path = sec.CACHE_DIR / f"segmentos_q_{int(cik):010d}.json.gz"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_h * 3600:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return pd.DataFrame(json.load(f))
    s = sec.submissions(int(cik))
    r = s.get("filings", {}).get("recent", {})
    accs = [r["accessionNumber"][i] for i, f in enumerate(r.get("form", [])) if f in ("10-Q", "10-K")][:n_filings]
    rows = []
    for k, acc in enumerate(accs):
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        try:
            items = [x["name"] for x in sec._get(base + "index.json").json()["directory"]["item"]]
            inst = [x for x in items if x.endswith("_htm.xml")] or [x for x in items if re.search(r"\d{8}\.xml$", x)]
            lab = [x for x in items if x.endswith("_lab.xml")]
            if not inst:
                continue
            labels = _labels(base + lab[0]) if lab else {}
            for x in _parse(sec._get(base + inst[0]).content, labels, quarterly=True):
                x["Prioridad"] = k
                rows.append(x)
        except Exception:  # noqa: BLE001
            continue
    df = pd.DataFrame(rows)
    out = []
    if not df.empty:
        df = df.sort_values("Prioridad")
        df["Miembro"] = df["Id"].map(df.drop_duplicates("Id").set_index("Id")["Miembro"]).map(_clean_label)
        df = df.drop_duplicates(["Tipo", "Dato", "Miembro", "Inicio", "Fin"])
        for (tp, dato, mid), g in df.groupby(["Tipo", "Dato", "Miembro"]):
            per = {(a, b): v for a, b, v in zip(g["Inicio"], g["Fin"], g["Valor"])}
            q = {b: v for (a, b), v in per.items() if 80 < (date.fromisoformat(b) - date.fromisoformat(a)).days < 100}
            for (a, b), v in per.items():  # 4.º trimestre = año − 9 meses
                if 350 < (date.fromisoformat(b) - date.fromisoformat(a)).days < 380 and b not in q:
                    nine = [vv for (aa, bb), vv in per.items() if aa == a and 260 < (date.fromisoformat(bb) - date.fromisoformat(aa)).days < 285]
                    if nine:
                        q[b] = v - nine[0]
            name = g["Miembro"].iloc[0]
            out += [{"Tipo": tp, "Dato": dato, "Miembro": name, "Fin": b, "Valor": v} for b, v in q.items()]
    res = pd.DataFrame(out)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(res.to_dict("records"), f)
    return res
