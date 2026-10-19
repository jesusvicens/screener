"""Tus listas de seguimiento (A analizar, Analizadas, Para más adelante, Caras…) y la prioridad de análisis.

Se guardan en el documento «_LISTAS» del almacenamiento (tu repo privado de datos online):
    {"grupos": ["A analizar", ...],
     "empresas": {"ADBE": {"grupo": "Analizadas", "añadida": "2026-10-16", "comentario": "", "objetivo": 380.0}}}
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import storage

DOC = "_LISTAS"
DEFAULT_GROUPS = ["A analizar", "Analizadas", "Para más adelante", "Caras (esperar precio)", "Descartadas"]


def _norm(e: dict) -> dict:
    """Una empresa puede estar en varias listas. Migra el formato antiguo (un solo «grupo»)."""
    ls = list(e.get("listas") or [])
    if e.get("grupo") and e["grupo"] not in ls:
        ls.append(e["grupo"])
    e.pop("grupo", None)
    e["listas"] = ls
    e.setdefault("comentario", "")
    e.setdefault("objetivo", None)
    return e


def load() -> dict:
    d = storage.load(DOC) or {}
    grupos = d.get("grupos") or list(DEFAULT_GROUPS)
    emp = {t: _norm(dict(e)) for t, e in (d.get("empresas") or {}).items()}
    for e in emp.values():  # listas que solo aparecen en empresas (por si se borró de la lista de listas)
        for g in e["listas"]:
            if g not in grupos:
                grupos.append(g)
    return {"grupos": grupos, "empresas": {t: e for t, e in emp.items() if e["listas"]}}


def save(d: dict) -> str:
    emp = {t: e for t, e in d["empresas"].items() if e.get("listas")}
    return storage.save(DOC, {"grupos": d["grupos"], "empresas": emp})


def add(d: dict, tickers: list[str], grupo: str, objetivo: float | None = None) -> dict:
    """Añade las empresas a la lista (sin sacarlas de las otras en las que estén)."""
    for t in tickers:
        t = t.upper()
        e = d["empresas"].get(t) or {"añadida": date.today().isoformat(), "comentario": "", "objetivo": None, "listas": []}
        e = _norm(e)
        if grupo not in e["listas"]:
            e["listas"].append(grupo)
        if objetivo is not None:
            e["objetivo"] = objetivo
        d["empresas"][t] = e
    return d


def remove_from(d: dict, ticker: str, grupo: str) -> dict:
    e = d["empresas"].get(ticker.upper())
    if e:
        e["listas"] = [g for g in e.get("listas", []) if g != grupo]
        if not e["listas"]:
            d["empresas"].pop(ticker.upper(), None)
    return d


def remove(d: dict, tickers: list[str]) -> dict:
    for t in tickers:
        d["empresas"].pop(t.upper(), None)
    return d


def set_lists(d: dict, ticker: str, grupos: list[str]) -> dict:
    t = ticker.upper()
    if not grupos:
        d["empresas"].pop(t, None)
        return d
    e = _norm(d["empresas"].get(t) or {"añadida": date.today().isoformat()})
    e["listas"] = list(grupos)
    d["empresas"][t] = e
    return d


def lists_of(d: dict, ticker: str) -> list[str]:
    return list((d["empresas"].get(ticker.upper()) or {}).get("listas") or [])


def in_list(d: dict, grupo: str) -> list[str]:
    return sorted(t for t, e in d["empresas"].items() if grupo in (e.get("listas") or []))


# ---------------------------------------------------------------- prioridad
PESO_NOTA = 0.7
PESO_PRECIO = 0.3


def prioridad(df: pd.DataFrame) -> pd.Series:
    return prioridad_detalle(df)["Prioridad"]


BLOQUES = {"Nota PyG": "PyG", "Nota Balance": "Balance", "Nota Cash Flow": "Cash Flow", "Nota Asignación de capital": "Asignación de capital"}


def prioridad_detalle(df: pd.DataFrame) -> pd.DataFrame:
    """Prioridad y sus piezas: puntos por nota, puntos por precio y el motivo en palabras."""
    nota = pd.to_numeric(df["Nota financiera"], errors="coerce")
    rfcf = pd.to_numeric(df.get("Rent. FCF"), errors="coerce") if "Rent. FCF" in df else pd.Series(index=df.index, dtype=float)
    per = pd.to_numeric(df.get("PER"), errors="coerce") if "PER" in df else pd.Series(index=df.index, dtype=float)
    fiable = ~((rfcf > 0.30) | ((per > 0) & (per < 3))) & rfcf.notna()
    rf = rfcf.where(fiable)
    pctl = rf.rank(pct=True)
    barata = (pctl * 10).fillna(5.0)
    nval = int(rf.notna().sum())
    mas_barata = (rf.rank(method="min") - 1) / max(nval - 1, 1)
    out = pd.DataFrame(index=df.index)
    out["Puntos por nota"] = (PESO_NOTA * nota).round(2)
    out["Puntos por precio"] = (PESO_PRECIO * barata).round(2)
    out["Prioridad"] = (out["Puntos por nota"] + out["Puntos por precio"]).round(2)
    out["Precio (0-10)"] = barata.round(1)
    motivos = []
    for i in df.index:
        partes = []
        n = nota.get(i)
        bl = {lab: pd.to_numeric(df.at[i, c], errors="coerce") for c, lab in BLOQUES.items() if c in df}
        bl = {k: v for k, v in bl.items() if pd.notna(v)}
        if pd.notna(n):
            txt = f"Nota {n:.1f}/10"
            if bl:
                best = max(bl, key=bl.get)
                worst = min(bl, key=bl.get)
                txt += f": lo mejor, {best} ({bl[best]:.1f})"
                if worst != best and bl[worst] < 8:
                    txt += f"; lo más flojo, {worst} ({bl[worst]:.1f})"
            partes.append(txt)
        if fiable.get(i, False):
            p = mas_barata.get(i)
            if rfcf.get(i) < 0:
                partes.append(f"quema caja libre ({rfcf.get(i):.1%} de su capitalización): de las peores en precio")
            else:
                partes.append(f"su caja libre rinde un {rfcf.get(i):.1%} de lo que vale en bolsa: más barata que el {p:.0%} de las candidatas")
        elif pd.notna(rfcf.get(i)):
            partes.append("dato de precio poco fiable (otra divisa o split): el precio cuenta como término medio")
        else:
            partes.append("sin cotización o sin caja libre positiva: el precio cuenta como término medio")
        motivos.append(" · ".join(partes))
    out["Motivo"] = motivos
    return out


def _prioridad_simple(df: pd.DataFrame) -> pd.Series:
    """Prioridad 0-10 = 70 % nota financiera + 30 % lo barata que está frente al resto de candidatas.

    «Barata» = posición (percentil) de la rentabilidad por flujo de caja libre (FCF / capitalización)
    dentro de las candidatas: la más barata saca 10 y la más cara 0. Sin precio, o con un dato que no
    se sostiene (rentabilidad FCF > 30 % o PER < 3: suele ser otra divisa o un split mal casado),
    cuenta como término medio (5).
    """
    nota = pd.to_numeric(df["Nota financiera"], errors="coerce")
    rfcf = pd.to_numeric(df.get("Rent. FCF"), errors="coerce") if "Rent. FCF" in df else pd.Series(index=df.index, dtype=float)
    per = pd.to_numeric(df.get("PER"), errors="coerce") if "PER" in df else pd.Series(index=df.index, dtype=float)
    rfcf = rfcf.where(~((rfcf > 0.30) | ((per > 0) & (per < 3))))
    barata = (rfcf.rank(pct=True) * 10).fillna(5.0)
    return (PESO_NOTA * nota + PESO_PRECIO * barata).round(2)
