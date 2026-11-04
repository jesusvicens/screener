"""Herramientas de la tarea diaria de análisis cualitativos (la ejecuta Claude, no la app).

  python scripts/candidatas.py cola --datos ../terminal-datos --n 50
      → las siguientes N empresas a puntuar (JSON), en orden de prioridad (85 % parte financiera —nota financiera y «calidad que crece»— + 15 % precio; la cualitativa,
        que aún no tienen, cuenta igual para todas) entre las de nota financiera ≥ 7,5, como mucho 3 preguntas «no aplica» y
        ventas ≥ 300 M$ (EE. UU. y Europa). Fuera: las descartadas, las que ya tienen tu examen cualitativo y las puntuadas
        por Claude en los últimos 180 días (después se repasan, las más antiguas primero).
  python scripts/candidatas.py contexto TICKER
      → datos cuantitativos de la empresa para el analista (ventas, márgenes, ROIC, notas…).
  python scripts/candidatas.py guardar fichero.json --datos ../terminal-datos
      → valida el análisis, calcula la nota cualitativa, lo guarda en data/candidatas/ y actualiza el índice.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from terminal import exam as E, listas, screener  # noqa: E402

QIDS = [q[0] for q in E.QUESTIONS if q[1] in E.QUALITATIVE_BLOCKS]
REPASO_DIAS = 180


def _universo() -> pd.DataFrame:
    screener.sync_from_repo()
    base = screener.load_base(9999)
    mk, _ = screener.load_market()
    df = screener.with_notas(screener.with_valuation(base, mk))
    return screener.with_avg_growth(df)


def _excluidas(datos: Path) -> set[str]:
    out = set()
    li = json.loads((datos / "data/analisis/_LISTAS.json").read_text("utf-8"))
    out |= {t.upper() for t, e in li.get("empresas", {}).items() if "Descartadas" in (e.get("listas") or [])}
    for p in (datos / "data/analisis").glob("[!_]*.json"):     # ya tienen tu examen cualitativo
        try:
            ex = json.loads(p.read_text("utf-8")).get("examen") or {}
        except Exception:  # noqa: BLE001
            continue
        if any(ex.get(q) for q in QIDS):
            out.add(p.stem.upper())
    idx = _indice(datos)
    hoy = date.today()
    for t, e in idx.get("empresas", {}).items():
        try:
            if (hoy - date.fromisoformat(e.get("fecha", "2000-01-01"))).days < REPASO_DIAS:
                out.add(t.upper())
        except ValueError:
            pass
    return out


def _indice(datos: Path) -> dict:
    p = datos / "data/candidatas/_INDICE.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"empresas": {}}


def cola(datos: Path, n: int) -> list[dict]:
    df = _universo()
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(float("nan"), index=df.index)  # noqa: E731
    excl = _excluidas(datos)
    libre = ~df["Ticker"].astype(str).str.upper().isin(excl)
    rec = (num("Nota financiera") >= 7.5) & (num("Preguntas no aplicables").fillna(99) <= 3) & (num("Ventas (M$)") >= 300)
    todas = df[rec].drop_duplicates("Ticker").copy()
    det = listas.prioridad_detalle(todas)               # precio relativo entre todas las candidatas, no solo las pendientes
    todas["Prioridad"] = det["Prioridad"]
    viejas = {t: e.get("fecha", "") for t, e in _indice(datos).get("empresas", {}).items()}
    pend = todas[libre[todas.index]].copy()
    pend["_viejo"] = pend["Ticker"].map(lambda t: viejas.get(t, ""))   # nunca puntuadas ("") primero; después, las más antiguas
    pend = pend.sort_values(["_viejo", "Prioridad"], ascending=[True, False])
    return [{"ticker": r["Ticker"], "empresa": r["Empresa"], "prioridad": round(float(r["Prioridad"]), 2),
             "repaso": bool(r["_viejo"])} for _, r in pend.head(n).iterrows()]


def contexto(ticker: str) -> dict:
    df = _universo()
    r = df[df["Ticker"].astype(str).str.upper() == ticker.upper()]
    if r.empty:
        return {"ticker": ticker, "error": "no está en el screener"}
    r = r.iloc[0]
    cols = ["Empresa", "Mercado", "País", "Sector", "Industria", "Año datos", "Ventas (M$)", "Beneficio (M$)", "Capitalización (M$)",
            "CAGR ventas 5a", "CAGR BPA 5a", "Margen bruto", "Margen operativo", "Margen FCF", "ROE medio 5a", "ROIC normalizado",
            "ROIC incremental", "Tasa de reinversión", "Deuda / patrimonio", "Var. acciones 5a", "SBC / FCF", "PER", "P/FCF",
            "Nota financiera", "Nota PyG", "Nota Balance", "Nota Cash Flow", "Nota Asignación de capital", "Margen de seguridad"]
    out = {"ticker": ticker.upper()}
    for c in cols:
        v = r.get(c)
        out[c] = None if (v is None or (isinstance(v, float) and v != v)) else (round(float(v), 4) if isinstance(v, (int, float)) else str(v))
    return out


def guardar(fichero: Path, datos: Path) -> str:
    a = json.loads(fichero.read_text("utf-8"))
    t = str(a.get("ticker", "")).upper()
    if not t:
        raise SystemExit("Falta «ticker».")
    ex = {k: int(v) for k, v in (a.get("examen") or {}).items() if k in QIDS and v is not None}
    malas = [k for k, v in ex.items() if v not in (0, 1, 2, 3)]
    falta = [q for q in QIDS if q not in ex]
    if malas or falta:
        raise SystemExit(f"Examen incompleto o con valores fuera de 0-3: faltan {falta}, mal {malas}")
    mot = a.get("motivos") or {}
    sin_motivo = [q for q in QIDS if not str(mot.get(q, "")).strip()]
    if sin_motivo:
        raise SystemExit(f"Faltan motivos en {sin_motivo}")
    cortos = [q for q in QIDS if len(str(mot.get(q, "")).strip()) < 40]
    if cortos:
        raise SystemExit(f"Motivos demasiado cortos (mínimo una frase con el hecho y la fuente) en {cortos}")
    for k in ("en_una_frase", "veredicto"):
        if not str(a.get(k, "")).strip():
            raise SystemExit(f"Falta «{k}».")
    sc = E.score(ex)
    a["ticker"], a["examen"] = t, ex
    a["nota_cualitativa"] = round(sc["cualitativa"], 2)
    a["notas_bloque"] = {b: (round(sc["blocks"][b]["nota"], 2) if sc["blocks"][b]["nota"] is not None else None) for b in E.QUALITATIVE_BLOCKS}
    a.setdefault("fecha", date.today().isoformat())
    a.setdefault("tipo", "test rápido")
    d = datos / "data/candidatas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{t}.json").write_text(json.dumps(a, ensure_ascii=False, indent=2), "utf-8")
    idx = _indice(datos)
    idx.setdefault("empresas", {})[t] = {k: a.get(k) for k in ("fecha", "empresa", "tipo", "nota_cualitativa", "notas_bloque", "en_una_frase", "veredicto", "alertas")}
    idx["actualizado"] = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M")
    (d / "_INDICE.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), "utf-8")
    return f"{t}: nota cualitativa {a['nota_cualitativa']:.2f}"


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("cola")
    c.add_argument("--datos", type=Path, required=True)
    c.add_argument("--n", type=int, default=50)
    x = sp.add_parser("contexto")
    x.add_argument("ticker")
    g = sp.add_parser("guardar")
    g.add_argument("fichero", type=Path)
    g.add_argument("--datos", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "cola":
        print(json.dumps(cola(a.datos, a.n), ensure_ascii=False, indent=1))
    elif a.cmd == "contexto":
        print(json.dumps(contexto(a.ticker), ensure_ascii=False, indent=1))
    else:
        print(guardar(a.fichero, a.datos))


if __name__ == "__main__":
    main()
