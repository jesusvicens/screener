"""Carteras de superinversores según sus formularios 13F (posiciones en acciones de EE. UU. al cierre de cada trimestre).

El 13F se presenta hasta 45 días después del trimestre: es una foto con retraso, no lo que tienen hoy.
Se prepara cada semana en GitHub Actions (rama «datos») y, si no está, se calcula aquí (≈1 minuto).
"""
from __future__ import annotations

import io
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from . import sec

# nombre visible → (CIK del 13F, gestor)
FUNDS: dict[str, tuple[int, str]] = {
    "Berkshire Hathaway": (1067983, "Warren Buffett"),
    "Markel Group": (1096343, "Tom Gayner"),
    "Akre Capital": (1112520, "Chuck Akre / John Neff"),
    "Pershing Square": (1336528, "Bill Ackman"),
    "Baupost Group": (1061768, "Seth Klarman"),
    "Himalaya Capital": (1709323, "Li Lu"),
    "Gardner Russo & Quinn": (860643, "Tom Russo"),
    "Giverny Capital": (1641864, "François Rochon"),
    "Polen Capital": (1034524, "Dan Davidowitz"),
    "Fundsmith": (1569205, "Terry Smith"),
    "Lindsell Train": (1484150, "Nick Train"),
    "Oaktree Capital": (949509, "Howard Marks"),
    "Dalal Street (Pabrai)": (1549575, "Mohnish Pabrai"),
    "Semper Augustus": (1115373, "Christopher Bloomstran"),
    "Ruane Cunniff (Sequoia)": (1720792, "Ruane, Cunniff & Goldfarb"),
    "Harris Associates (Oakmark)": (813917, "Bill Nygren"),
    "Tweedy, Browne": (732905, "Tweedy, Browne"),
    "H&H International": (1759760, "Duan Yongping"),
    "Davis Advisers": (1036325, "Chris Davis"),
    "Dodge & Cox": (200217, "Dodge & Cox"),
    "TCI Fund": (1647251, "Chris Hohn"),
    "ValueAct": (1418814, "Mason Morfit"),
    "Durable Capital": (1798849, "Henry Ellenbogen"),
    "Wedgewood Partners": (859804, "David Rolfe"),
}

FILE = sec.CACHE_DIR / "superinversores.parquet"
STOP = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "HLDGS", "HOLDINGS", "HLDG",
        "GROUP", "GRP", "THE", "CL", "CLASS", "A", "B", "C", "COM", "NEW", "DEL", "SHS", "ORD", "SA", "NV", "AG", "LP", "N", "V"}


def norm(name: str) -> str:
    n = re.sub(r"/[A-Z]{2,3}/?", " ", (name or "").upper()).replace("'", "").replace("’", "").replace(".", "")
    w = re.sub(r"[^A-Z0-9 ]", " ", n.replace("&", " ")).split()
    return " ".join(x for x in w if x not in STOP)


def _13f_list(cik: int, n: int = 2) -> list[tuple[str, str, str]]:
    s = sec.submissions(cik, max_age_h=24 * 3)
    r = s.get("filings", {}).get("recent", {})
    out = []
    for i, f in enumerate(r.get("form", [])):
        if f == "13F-HR":
            out.append((r["accessionNumber"][i], r["reportDate"][i], r["filingDate"][i]))
        if len(out) >= n:
            break
    return out


def _holdings(cik: int, acc: str) -> pd.DataFrame:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    items = sec._get(base + "index.json").json()["directory"]["item"]
    xmls = [x["name"] for x in items if x["name"].endswith(".xml") and "primary_doc" not in x["name"]]
    if not xmls:
        return pd.DataFrame()
    root = ET.fromstring(sec._get(base + xmls[0]).content)
    for el in root.iter():  # quita los espacios de nombres de las etiquetas
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    rows = []
    for it in root.iter("infoTable"):
        g = lambda p: (it.find(p).text.strip() if it.find(p) is not None and it.find(p).text else None)  # noqa: E731
        if (g("putCall") or "").strip():
            continue  # opciones fuera
        rows.append({"emisor": g("nameOfIssuer"), "cusip": g("cusip"), "valor": float(g("value") or 0),
                     "acciones": float(g("shrsOrPrnAmt/sshPrnamt") or 0)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("cusip", as_index=False).agg(emisor=("emisor", "first"), valor=("valor", "sum"), acciones=("acciones", "sum"))


def build(progress=None) -> pd.DataFrame:
    """Última cartera de cada fondo con la variación frente al trimestre anterior."""
    frames = []
    for k, (name, (cik, mgr)) in enumerate(FUNDS.items()):
        if progress:
            progress(k / len(FUNDS), f"13F de {name}")
        try:
            fl = _13f_list(cik)
            if not fl:
                continue
            cur = _holdings(cik, fl[0][0])
            prev = _holdings(cik, fl[1][0]) if len(fl) > 1 else pd.DataFrame(columns=["cusip", "acciones", "emisor", "valor"])
        except Exception:  # noqa: BLE001
            continue
        if cur.empty:
            continue
        tot = cur["valor"].sum()
        m = cur.merge(prev[["cusip", "acciones"]].rename(columns={"acciones": "acciones_prev"}), on="cusip", how="left")
        gone = prev[~prev["cusip"].isin(cur["cusip"])].assign(valor=0.0, acciones_prev=lambda d: d["acciones"], acciones=0.0)
        m = pd.concat([m, gone[["cusip", "emisor", "valor", "acciones", "acciones_prev"]]], ignore_index=True)
        m["peso"] = m["valor"] / tot if tot else None
        m["fondo"], m["gestor"], m["trimestre"], m["presentado"] = name, mgr, fl[0][1], fl[0][2]
        m["n_posiciones"] = len(cur)
        frames.append(m)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        df["clave"] = df["emisor"].map(norm)
    return df


def load(max_age_days: float = 8) -> pd.DataFrame | None:
    if FILE.exists() and (time.time() - FILE.stat().st_mtime) < max_age_days * 86400:
        return pd.read_parquet(FILE)
    try:
        from . import remoto
        raw = remoto.public_file("superinversores.parquet")
        if raw:
            FILE.write_bytes(raw)
            return pd.read_parquet(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        pass
    return pd.read_parquet(FILE) if FILE.exists() else None


def save(df: pd.DataFrame):
    df.to_parquet(FILE)


def holders(df: pd.DataFrame, company_name: str) -> pd.DataFrame:
    """Fondos que tienen la empresa (por nombre; se completa con los CUSIP encontrados)."""
    if df is None or df.empty:
        return pd.DataFrame()
    key = norm(company_name)
    if not key:
        return pd.DataFrame()
    hit = df[df["clave"] == key]
    if hit.empty:  # p. ej. «ALPHABET INC CAP STK CL C»
        hit = df[df["clave"].str.startswith(key + " ")]
    cus = set(hit["cusip"])
    h = df[df["cusip"].isin(cus)].copy()
    if h.empty:
        return h

    def _chg(r):
        a, p = r["acciones"], r["acciones_prev"]
        if a == 0:
            return "Vendida"
        if p is None or p != p or p == 0:
            return "Nueva"
        x = a / p - 1
        return "Sube" if x > 0.02 else ("Baja" if x < -0.02 else "Igual")

    h["Cambio"] = h.apply(_chg, axis=1)
    h["Var. acciones"] = [(a / p - 1) if (p and p == p and a) else None for a, p in zip(h["acciones"], h["acciones_prev"])]
    return h.sort_values(["peso"], ascending=False)
