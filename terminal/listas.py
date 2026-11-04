"""Tus listas de seguimiento (En cartera, A analizar, Caras, Descartadas, Seguir de cerca, Aceptadas) y la prioridad de análisis.

Se guardan en el documento «_LISTAS» del almacenamiento (tu repo privado de datos online):
    {"grupos": ["A analizar", ...],
     "empresas": {"ADBE": {"grupo": "Analizadas", "añadida": "2026-10-16", "comentario": "", "objetivo": 380.0}}}
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import storage

DOC = "_LISTAS"
CARTERA = "En cartera"
DEFAULT_GROUPS = [CARTERA, "A analizar", "Caras (esperar precio)", "Descartadas", "Seguir de cerca", "Aceptadas"]
RENOMBRAR = {"Analizadas": "Aceptadas", "Para más adelante": "Seguir de cerca"}  # nombres antiguos → nuevos


def _norm(e: dict) -> dict:
    """Una empresa puede estar en varias listas. Migra el formato antiguo (un solo «grupo»)."""
    ls = list(e.get("listas") or [])
    if e.get("grupo") and e["grupo"] not in ls:
        ls.append(e["grupo"])
    ls = list(dict.fromkeys(RENOMBRAR.get(g, g) for g in ls))
    e.pop("grupo", None)
    e["listas"] = ls
    e.setdefault("comentario", "")
    e.setdefault("objetivo", None)
    return e


def load() -> dict:
    d = storage.load(DOC) or {}
    viejos = [RENOMBRAR.get(g, g) for g in (d.get("grupos") or [])]
    grupos = list(DEFAULT_GROUPS) + [g for g in dict.fromkeys(viejos) if g not in DEFAULT_GROUPS]
    emp = {t: _norm(dict(e)) for t, e in (d.get("empresas") or {}).items()}
    for e in emp.values():  # listas que solo aparecen en empresas (por si se borró de la lista de listas)
        for g in e["listas"]:
            if g not in grupos:
                grupos.append(g)
    if CARTERA not in grupos:  # «En cartera» siempre existe y va la primera
        grupos.insert(0, CARTERA)
    else:
        grupos.insert(0, grupos.pop(grupos.index(CARTERA)))
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
PESO_NOTA = 0.85
PESO_PRECIO = 0.15
# Con nota cualitativa (análisis de Claude o tuyo): 45 % cualitativa + 40 % financiera + 15 % precio. Lo que manda es
# la calidad del negocio; el precio solo desempata entre empresas parecidas (el margen de seguridad se mira después).
PESO_NOTA_Q, PESO_CUAL_Q, PESO_PRECIO_Q = 0.40, 0.45, 0.15


def prioridad(df: pd.DataFrame) -> pd.Series:
    return prioridad_detalle(df)["Prioridad"]


BLOQUES = {"Nota PyG": "PyG", "Nota Balance": "Balance", "Nota Cash Flow": "Cash Flow", "Nota Asignación de capital": "Asignación de capital"}


def _crec_robusto(serie, n: int = 5) -> float:
    """Crecimiento anual a n años entre medias de dos años (años L-n-1/L-n frente a L-1/L).

    Así un año extraordinario en el punto de partida (p. ej. el beneficio fiscal de Adobe en 2020) o en el final no
    infla ni hunde el crecimiento. Sin los n+2 años, o con alguna de las medias negativa, devuelve NaN: una empresa
    con poca historia no puntúa como si creciera mucho (cuenta 5, neutro)."""
    try:
        a = np.asarray(serie, dtype=float)
    except Exception:  # noqa: BLE001
        return float("nan")
    if a.ndim != 1 or len(a) < n + 2:
        return float("nan")
    ini, fin = a[-(n + 2):-n], a[-2:]
    if not (np.isfinite(ini).all() and np.isfinite(fin).all()):
        return float("nan")
    i, f = ini.mean(), fin.mean()
    if i <= 0 or f <= 0:
        return float("nan")
    tramo = a[-(n + 2):]
    if (tramo <= 0).any():
        pass  # un año con pérdidas dentro del tramo es posible; las medias ya lo recogen
    else:
        saltos = tramo[1:] / tramo[:-1]
        if (saltos > 20).any() or (saltos < 0.05).any():
            return float("nan")  # salto de escala en los datos (unidades frente a millones, cambio de etiqueta)
    return float((f / i) ** (1 / n) - 1)


def calidad_que_crece(df: pd.DataFrame) -> pd.Series:
    """0-10 «al estilo Fisher» dentro del grupo: cuánto crece y con qué márgenes y regularidad.

    45 % crecimiento, 40 % rentabilidad (margen operativo, margen de caja libre y ROIC o, si falta, ROE medio) y
    15 % regularidad (años con caída de ventas y de BPA). Cada dato se puntúa por su posición (percentil) entre las
    candidatas; sin dato cuenta 5.

    Crecimiento: ventas, beneficio neto y caja libre a 5 años, medidos entre medias de dos años (ver `_crec_robusto`), con tope
    del 40 %. Solo cuenta entero si la rentabilidad está al menos en la media del grupo: crecer mucho con márgenes
    flojos vale menos (con la rentabilidad más baja, la mitad). Materias primas, navieras, constructoras de viviendas e
    inmobiliarias puntúan un 30 % menos: sus márgenes y su crecimiento salen de un ciclo favorable o de revalorizaciones,
    no de una ventaja duradera.
    """
    def num(c):
        return pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(float("nan"), index=df.index)

    def pct(s, alto_mejor=True):
        r = s.rank(pct=True, ascending=alto_mejor)
        return (r * 10).fillna(5.0)

    def robusto(col_serie, col_cagr):
        """Con la serie anual, el crecimiento robusto; si la empresa no tiene serie (algunas europeas), el CAGR."""
        if col_serie not in df:
            return num(col_cagr)
        def sin_serie(x):
            try:
                return not np.isfinite(np.asarray(x, dtype=float)).any()
            except Exception:  # noqa: BLE001
                return True
        g = df[col_serie].map(_crec_robusto)
        return g.where(~df[col_serie].map(sin_serie), num(col_cagr))

    # Beneficio neto y no BPA: la serie de BPA no está ajustada por splits (Alphabet 20:1 en 2022) y saldría negativa.
    g_rev = robusto("_s_rev", "CAGR ventas 5a")
    g_ben = robusto("_s_ni", "CAGR beneficio 5a")
    g_fcf = robusto("_s_fcf", "CAGR FCF 5a")
    crec = (pct(g_rev.clip(upper=0.4)) + pct(g_ben.clip(upper=0.4)) + pct(g_fcf.clip(upper=0.4))) / 3
    rent_cap = num("ROIC").where(num("ROIC").between(-1, 1.5)).fillna(num("ROE medio 5a"))
    rent = (pct(num("Margen operativo").where(num("Margen operativo") <= 0.8)) + pct(num("Margen FCF").where(num("Margen FCF") <= 0.8))
            + pct(rent_cap)) / 3
    crec = crec * (0.5 + rent / 10).clip(upper=1.0)
    reg = (pct(num("Años caída ventas"), alto_mejor=False) + pct(num("Años caída BPA"), alto_mejor=False)) / 2
    score = 0.45 * crec + 0.40 * rent + 0.15 * reg
    ciclica = es_ciclica(df)
    return score.where(~ciclica, score * 0.7).round(2)


CICLICAS = ("oil", "gas", "petroleum", "marine", "shipping", "mining", "gold", "silver", "steel", "metal", "coal",
            "uranium", "fertilizer", "agricultural chemicals", "homebuilding", "residential construction", "copper",
            "aluminum", "paper", "lumber", "tanker", "real estate", "reit")


def es_ciclica(df: pd.DataFrame) -> pd.Series:
    ind = df.get("Industria", pd.Series("", index=df.index)).astype(str).str.lower()
    sec = df.get("Sector", pd.Series("", index=df.index)).astype(str).str.lower()
    m = ind.apply(lambda x: any(k in x for k in CICLICAS))
    return m | sec.isin(["energy", "basic materials"])


def prioridad_detalle(df: pd.DataFrame) -> pd.DataFrame:
    """Prioridad y sus piezas: puntos por nota, puntos por precio y el motivo en palabras.

    La parte «financiera» es la media de tu nota financiera (examen de 21 preguntas) y de la «calidad que crece»
    (crecimiento, márgenes y regularidad frente al resto de candidatas): así una empresa que crece mucho con márgenes
    enormes pasa por delante de otra igual de sana pero que apenas crece."""
    nota_ex = pd.to_numeric(df["Nota financiera"], errors="coerce")
    fisher = calidad_que_crece(df)
    nota = (0.4 * nota_ex + 0.6 * fisher).where(nota_ex.notna(), fisher)
    rfcf = pd.to_numeric(df.get("Rent. FCF"), errors="coerce") if "Rent. FCF" in df else pd.Series(index=df.index, dtype=float)
    per = pd.to_numeric(df.get("PER"), errors="coerce") if "PER" in df else pd.Series(index=df.index, dtype=float)
    fiable = ~((rfcf > 0.30) | ((per > 0) & (per < 3))) & rfcf.notna()
    rf = rfcf.where(fiable)
    pctl = rf.rank(pct=True)
    barata = (pctl * 10).fillna(5.0)
    nval = int(rf.notna().sum())
    mas_barata = (rf.rank(method="min") - 1) / max(nval - 1, 1)
    out = pd.DataFrame(index=df.index)
    cual = pd.to_numeric(df["Nota cualitativa"], errors="coerce") if "Nota cualitativa" in df else None
    if cual is not None:
        # sin análisis cualitativo todavía: cuenta como término medio (5), igual que el precio sin dato
        out["Puntos por nota"] = (PESO_NOTA_Q * nota).round(2)
        out["Puntos por cualitativo"] = (PESO_CUAL_Q * cual.fillna(5.0)).round(2)
    else:
        out["Puntos por nota"] = (PESO_NOTA * nota).round(2)
        out["Puntos por cualitativo"] = 0.0
    out["Puntos por precio"] = ((PESO_PRECIO_Q if cual is not None else PESO_PRECIO) * barata).round(2)
    out["Prioridad"] = (out["Puntos por nota"] + out["Puntos por cualitativo"] + out["Puntos por precio"]).round(2)
    out["Precio (0-10)"] = barata.round(1)
    out["Calidad que crece"] = fisher
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
        if cual is not None:
            q = cual.get(i)
            partes.append(f"cualitativa {q:.1f}/10" if pd.notna(q) else "sin análisis cualitativo todavía (cuenta 5)")
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


def posiciones_abiertas(movimientos: list[dict]) -> list[str]:
    """Tickers con acciones en cartera según tus movimientos (compras − ventas, con splits)."""
    sh: dict[str, float] = {}
    for m in sorted(movimientos or [], key=lambda r: str(r.get("Fecha", ""))):
        t = str(m.get("Ticker") or "").upper()
        if not t:
            continue
        try:
            q = float(m.get("Acciones") or 0)
        except (TypeError, ValueError):
            continue
        tipo = m.get("Tipo")
        if tipo == "Compra":
            sh[t] = sh.get(t, 0) + q
        elif tipo == "Venta":
            sh[t] = sh.get(t, 0) - q
        elif tipo == "Split" and q > 0:
            sh[t] = sh.get(t, 0) * q
    return sorted(t for t, v in sh.items() if v > 1e-9)
