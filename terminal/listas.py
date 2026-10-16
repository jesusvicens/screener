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


def load() -> dict:
    d = storage.load(DOC) or {}
    grupos = d.get("grupos") or list(DEFAULT_GROUPS)
    emp = d.get("empresas") or {}
    for e in emp.values():  # grupos que solo aparecen en empresas (por si se borró de la lista)
        if e.get("grupo") and e["grupo"] not in grupos:
            grupos.append(e["grupo"])
    return {"grupos": grupos, "empresas": emp}


def save(d: dict) -> str:
    return storage.save(DOC, {"grupos": d["grupos"], "empresas": d["empresas"]})


def add(d: dict, tickers: list[str], grupo: str, objetivo: float | None = None) -> dict:
    for t in tickers:
        t = t.upper()
        e = d["empresas"].get(t) or {"añadida": date.today().isoformat(), "comentario": "", "objetivo": None}
        e["grupo"] = grupo
        if objetivo is not None:
            e["objetivo"] = objetivo
        d["empresas"][t] = e
    return d


def remove(d: dict, tickers: list[str]) -> dict:
    for t in tickers:
        d["empresas"].pop(t.upper(), None)
    return d


def group_of(d: dict, ticker: str) -> str | None:
    return (d["empresas"].get(ticker.upper()) or {}).get("grupo")


# ---------------------------------------------------------------- prioridad
PESO_NOTA = 0.7
PESO_PRECIO = 0.3


def prioridad(df: pd.DataFrame) -> pd.Series:
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
