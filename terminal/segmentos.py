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


def _parse(instance: bytes, labels: dict) -> list[dict]:
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
        if not 350 < days < 380:
            continue
        dims = [(d.split(":")[-1], m) for d, m in mem]
        main = [(d, m) for d, m in dims if d in AXES and AXES[d]]
        other = [(d, m) for d, m in dims if d not in AXES]
        if len(main) != 1 or other or any(d == "ConsolidationItemsAxis" and "Operating" not in m for d, m in dims):
            continue
        d, m = main[0]
        try:
            v = float(el.text)
        except (TypeError, ValueError):
            continue
        rows.append({"Tipo": AXES[d], "Dato": kind, "Id": m, "Miembro": labels.get(m) or _pretty(m), "Año": int(en[:4]), "Fin": en,
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
        df["Miembro"] = df["Id"].map(df.drop_duplicates("Id").set_index("Id")["Miembro"])
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
