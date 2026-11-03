"""Herramientas de la tarea diaria de análisis cualitativos (la ejecuta Claude, no la app).

  python scripts/candidatas.py cola --datos ../terminal-datos --n 5
      → las siguientes N empresas a analizar (JSON): primero «calidad que crece» (margen operativo ≥ 20 %, ventas a 5 años
        ≥ 10 % anual, ROIC incremental ≥ 15 %, nota financiera ≥ 8, ventas ≥ 500 M$); agotadas, las «Recomendadas» por
        prioridad (nota financiera ≥ 7,5). Nunca tus empresas (listas o análisis guardados), ni las ya analizadas por Claude
        en los últimos 180 días.
  python scripts/candidatas.py contexto TICKER
      → datos cuantitativos de la empresa para el analista (ventas, márgenes, ROIC, notas…).
  python scripts/candidatas.py guardar fichero.json --datos ../terminal-datos
      → valida el análisis, calcula la nota cualitativa, lo guarda en data/candidatas/ y actualiza el índice.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from terminal import exam as E, listas, screener  # noqa: E402

QIDS = [q[0] for q in E.QUESTIONS if q[1] in E.QUALITATIVE_BLOCKS]
SECCIONES = ["En una frase", "Negocio y cómo gana dinero", "Clientes, mercado y tamaño de la oportunidad", "Ventaja competitiva y su durabilidad",
             "Competidores", "Dirección, gobierno e incentivos", "Asignación de capital", "Palancas de crecimiento",
             "Cultura y empleados", "Riesgos: qué puede salir mal", "Qué vigilar", "Veredicto", "Fuentes"]
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
    out |= {t.upper() for t in li.get("empresas", {})}           # incluye «Descartadas»: no se analizan
    out |= {p.stem.upper() for p in (datos / "data/analisis").glob("[!_]*.json")}
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
    calidad = (num("Margen operativo") >= 0.20) & (num("CAGR ventas 5a") >= 0.10) & (num("ROIC incremental") >= 0.15) \
        & (num("Nota financiera") >= 8) & (num("Ventas (M$)") >= 500)
    rec = (num("Nota financiera") >= 7.5) & (num("Preguntas no aplicables").fillna(99) <= 3) & (num("Ventas (M$)") >= 300)
    out = []
    t1 = df[libre & calidad].copy()
    t1["_o"] = num("Nota financiera")[t1.index] + 5 * num("CAGR ventas 5a")[t1.index].fillna(0)
    for _, r in t1.sort_values("_o", ascending=False).iterrows():
        out.append({"ticker": r["Ticker"], "empresa": r["Empresa"], "motivo": "calidad que crece"})
    if len(out) < n:
        t2 = df[libre & rec & ~calidad].copy()
        det = listas.prioridad_detalle(t2)
        t2["Prioridad"] = det["Prioridad"]
        for _, r in t2.sort_values("Prioridad", ascending=False).iterrows():
            out.append({"ticker": r["Ticker"], "empresa": r["Empresa"], "motivo": "recomendadas (prioridad)"})
    return out[:n]


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
    dos = str(a.get("dossier", ""))
    if dos.count("### ") < 8 or len(dos) < 6000:
        raise SystemExit(f"Dossier demasiado corto ({len(dos)} caracteres, {dos.count('### ')} apartados): mínimo 6.000 y 8 apartados.")
    sc = E.score(ex)
    a["ticker"], a["examen"] = t, ex
    a["nota_cualitativa"] = round(sc["cualitativa"], 2)
    a["notas_bloque"] = {b: (round(sc["blocks"][b]["nota"], 2) if sc["blocks"][b]["nota"] is not None else None) for b in E.QUALITATIVE_BLOCKS}
    a.setdefault("fecha", date.today().isoformat())
    d = datos / "data/candidatas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{t}.json").write_text(json.dumps(a, ensure_ascii=False, indent=2), "utf-8")
    idx = _indice(datos)
    idx.setdefault("empresas", {})[t] = {k: a.get(k) for k in ("fecha", "empresa", "nota_cualitativa", "en_una_frase", "veredicto", "alertas")}
    idx["actualizado"] = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M")
    (d / "_INDICE.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), "utf-8")
    return f"{t}: nota cualitativa {a['nota_cualitativa']:.2f}"


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("cola")
    c.add_argument("--datos", type=Path, required=True)
    c.add_argument("--n", type=int, default=5)
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
