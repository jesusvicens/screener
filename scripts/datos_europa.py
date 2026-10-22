"""Cotizadas europeas para el screener (lo ejecuta GitHub Actions cada noche; publica en la rama «europa»).

1. Lista todos los informes ESEF del repositorio público filings.xbrl.org (≈27.000) y agrupa por empresa (LEI).
2. LEI → ISIN con el fichero público de GLEIF; ISIN → ticker de Yahoo con su buscador (solo acciones de bolsas
   europeas). Lo que ya está resuelto se guarda y no se repite; lo que falla se reintenta al cabo de 30 días.
3. Descarga los hechos de los informes (3 por empresa: el último y los de dos y cuatro años antes cubren 6 ejercicios)
   y calcula la fila del screener y las notas del examen financiero, como con las americanas.
4. Precios, divisas y tipos de cambio (Yahoo) cada noche.

Todo con un límite de tiempo (--minutos): la primera carga se completa en varias noches y luego solo hay que
procesar los informes nuevos. Salida en --out: europa_universo.json, europa_mapeo.json, europa_hechos.json.gz,
europa_base.parquet, europa_market.parquet, meta.json.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import io
import json
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from terminal import esef, financials as F, remoto, screener  # noqa: E402

BR = remoto.EUROPA_BRANCH
HOME = {"FR": ["PA"], "NL": ["AS"], "BE": ["BR"], "PT": ["LS"], "IE": ["IR", "L"], "ES": ["MC"], "IT": ["MI"],
        "DE": ["DE", "F"], "AT": ["VI"], "FI": ["HE"], "SE": ["ST"], "DK": ["CO"], "NO": ["OL"], "PL": ["WA"],
        "GR": ["AT"], "GB": ["L"], "UK": ["L"], "LU": ["PA", "AS", "BR", "DE", "ST"], "CZ": ["PR"], "HU": ["BD"],
        "IS": ["IC"], "EE": ["TL"], "LT": ["VS"], "LV": ["RG"], "CH": ["SW"], "MT": [], "CY": ["AT"], "HR": [], "SI": [],
        "RO": [], "BG": []}
NOW = datetime.now(timezone.utc)


def log(*a):
    print(*a, flush=True)


def prev_json(name, default):
    raw = remoto.public_file(name, branch=BR, timeout=120)
    if not raw:
        return default
    try:
        return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- 1. informes
def all_filings() -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    url = f"{esef.BASE}/api/filings?page%5Bsize%5D=500&page%5Bnumber%5D=1"
    n = 0
    while url:
        d = esef._get(url, timeout=120).json()
        for f in d.get("data", []):
            a = f["attributes"]
            rel = (f.get("relationships", {}).get("entity", {}).get("links", {}) or {}).get("related", "")
            lei = rel.rsplit("/", 1)[-1] if rel else (a.get("fxo_id") or "")[:20]
            if not lei or not a.get("json_url"):
                continue
            by.setdefault(lei, []).append({
                "id": f["id"], "period_end": a.get("period_end"), "country": a.get("country"), "added": a.get("date_added") or "",
                "published": a.get("published") or "", "json_url": a["json_url"], "viewer_url": a.get("viewer_url"),
                "report_url": a.get("report_url"), "errors": a.get("error_count") or 0})
            n += 1
        url = d.get("links", {}).get("next")
    log(f"Informes ESEF: {n:,} de {len(by):,} empresas")
    return by


def entity_names(leis: set[str], known: dict) -> dict[str, str]:
    """Nombre de cada LEI (API de entidades del repositorio, por páginas)."""
    out = {k: v for k, v in known.items() if k in leis}
    if len(out) >= len(leis):
        return out
    url = f"{esef.BASE}/api/entities?page%5Bsize%5D=500&page%5Bnumber%5D=1"
    while url:
        d = esef._get(url, timeout=120).json()
        for e in d.get("data", []):
            a = e["attributes"]
            if a.get("identifier") in leis:
                out[a["identifier"]] = a.get("name") or a["identifier"]
        url = d.get("links", {}).get("next")
    return out


# ---------------------------------------------------------------- 2. LEI → ISIN → ticker
def gleif_isins(leis: set[str]) -> dict[str, list[str]]:
    meta = requests.get("https://mapping.gleif.org/api/v2/isin-lei/latest", timeout=60).json()
    link = meta["data"]["attributes"]["downloadLink"]
    raw = requests.get(link, timeout=600).content
    out: dict[str, list[str]] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as fh:
            for row in csv.reader(io.TextIOWrapper(fh, encoding="utf-8")):
                if len(row) >= 2 and row[0] in leis:
                    out.setdefault(row[0], []).append(row[1])
    log(f"GLEIF: ISIN de {len(out):,} empresas")
    return out


def _yahoo_search(q: str) -> list[dict]:
    import yfinance as yf
    for i in range(3):
        try:
            return yf.Search(q, max_results=10, news_count=0).quotes or []
        except Exception:  # noqa: BLE001
            time.sleep(2 + 2 * i)
    return []


def _eu_equity(quotes: list[dict], country: str) -> dict | None:
    home = HOME.get(country, [])
    isin_like = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
    cands = [q for q in quotes if q.get("quoteType") == "EQUITY" and esef.is_european(q.get("symbol", ""))
             and not isin_like.match(q["symbol"].rsplit(".", 1)[0])]  # los bonos aparecen con el ISIN como símbolo
    if not cands:
        return None
    cands.sort(key=lambda q: (q["symbol"].rsplit(".", 1)[1] not in home, home.index(q["symbol"].rsplit(".", 1)[1])
                              if q["symbol"].rsplit(".", 1)[1] in home else 99))
    return cands[0]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(s\.?a\.?|se|plc|n\.?v\.?|ag|asa|ab|oyj|spa|s\.p\.a\.|sca|s\.c\.a\.|nv|sa/nv|group|holding|holdings|the|a/s)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def map_entity(lei: str, name: str, country: str, isins: list[str]) -> dict:
    """Busca la acción en Yahoo: primero por ISIN (fiable), después por nombre (exigiendo nombre parecido)."""
    pref = sorted(isins, key=lambda x: (not x.startswith(country[:2]), x))[:6] if len(isins) <= 60 else \
        [x for x in isins if x.startswith(country[:2])][:3]
    for isin in pref:
        q = _eu_equity(_yahoo_search(isin), country)
        if q:
            return {"ticker": q["symbol"], "isin": isin, "via": "isin", "yname": q.get("longname") or q.get("shortname")}
    q = _eu_equity(_yahoo_search(name), country)
    if q:
        sim = difflib.SequenceMatcher(None, _norm(name), _norm(q.get("longname") or q.get("shortname") or "")).ratio()
        if sim >= 0.72:
            return {"ticker": q["symbol"], "isin": None, "via": f"nombre ({sim:.2f})", "yname": q.get("longname") or q.get("shortname")}
    return {"ticker": None}


# ---------------------------------------------------------------- 3. hechos y filas
def pick3(filings: list[dict]) -> list[dict]:
    """El último informe y los de dos, cuatro y cinco ejercicios antes (cada uno trae también el año anterior)."""
    allf = esef.pick_filings(filings, max_reports=10)
    if not allf:
        return []
    out = [allf[0]]
    y0 = int((allf[0]["period_end"] or "0")[:4] or 0)
    for back in (2, 4, 5):  # (el año del repositorio a veces va desfasado: con el 5.º se cubre igual)
        c = [f for f in allf if int((f["period_end"] or "0")[:4] or 0) == y0 - back]
        if c:
            out.append(c[0])
    return out


def fetch(f: dict) -> tuple[str, list | None]:
    try:
        return f["json_url"], esef.compact(esef._get(f["json_url"], timeout=180).json())
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ {f['json_url']}: {e}")
        return f["json_url"], None


# ---------------------------------------------------------------- 4. precios
def yahoo_meta(tickers: list[str], deadline: float) -> dict[str, dict]:
    """Divisa, sector e industria de cada ticker nuevo (una consulta por empresa, solo la primera vez)."""
    import yfinance as yf

    def one(t):
        if time.time() > deadline:
            return t, None
        try:
            tk = yf.Ticker(t)
            cur = tk.fast_info.get("currency")
            try:
                info = tk.info or {}
            except Exception:  # noqa: BLE001
                info = {}
            if not cur and not info:
                return t, None
            return t, {"currency": cur or info.get("currency"), "sector": info.get("sector"), "industry": info.get("industry"),
                       "yname": info.get("longName")}
        except Exception:  # noqa: BLE001
            return t, None

    out = {}
    with ThreadPoolExecutor(4) as ex:
        for i, (t, r) in enumerate(ex.map(one, tickers)):
            if r:
                out[t] = r
            if i % 200 == 199:
                log(f"  Yahoo: {i + 1}/{len(tickers)}")
    return out


def last_prices(tickers: list[str]) -> dict[str, float]:
    import yfinance as yf
    out: dict[str, float] = {}
    for i in range(0, len(tickers), 200):
        chunk = tickers[i:i + 200]
        try:
            df = yf.download(chunk, period="7d", progress=False, auto_adjust=False, threads=True, group_by="column")
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        close = df["Close"] if "Close" in df else df
        if isinstance(close, pd.Series):
            close = close.to_frame(chunk[0])
        last = close.ffill().iloc[-1]
        for t, v in last.items():
            if pd.notna(v):
                out[str(t)] = float(v)
    return out


def fx_rates(currencies: set[str]) -> dict[str, float]:
    """Cuántos $ vale una unidad de cada divisa (GBp = peniques)."""
    import yfinance as yf
    out = {"USD": 1.0}
    need = sorted({c.upper() for c in currencies if c and c.upper() not in ("USD", "GBP")} | {"GBP"})
    pairs = [f"{c}USD=X" for c in need]
    try:
        df = yf.download(pairs, period="7d", progress=False, auto_adjust=False, group_by="column")["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(pairs[0])
        last = df.ffill().iloc[-1]
        for p, v in last.items():
            if pd.notna(v):
                out[str(p)[:3]] = float(v)
    except Exception as e:  # noqa: BLE001
        log(f"⚠ divisas: {e}")
    if "GBP" in out:
        out["GBp"] = out["GBX"] = out["GBP"] / 100
    return out


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out_europa")
    ap.add_argument("--minutos", type=float, default=40)
    ap.add_argument("--solo", help="LEI o tickers separados por comas (pruebas)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    now = NOW.isoformat(timespec="seconds")

    meta = prev_json("meta.json", {})
    mapeo: dict = prev_json("europa_mapeo.json", {})          # lei -> {ticker, isin, via, probado}
    hechos: dict = prev_json("europa_hechos.json.gz", {})     # json_url -> hechos compactos
    yinfo: dict = prev_json("europa_yahoo.json", {})          # ticker -> {currency, sector, industry}
    nombres: dict = prev_json("europa_nombres.json", {})
    log(f"Estado previo: {len(mapeo):,} empresas mapeadas, {len(hechos):,} informes guardados")

    filings = all_filings()
    # Empresas con algún informe de 2022 en adelante (las que siguen publicando).
    recent = {lei for lei, fl in filings.items() if any((f["period_end"] or "0") >= "2022-06-30" for f in fl)}
    if a.solo:
        want = set(a.solo.split(","))
        recent = {lei for lei in recent if lei in want or (mapeo.get(lei) or {}).get("ticker") in want}
    country = {lei: max(fl, key=lambda f: f["added"])["country"] for lei, fl in filings.items()}
    nombres = entity_names(recent, nombres)

    # --- mapeo a ticker
    pend = [lei for lei in recent if lei not in mapeo or (
        not mapeo[lei].get("ticker") and NOW - datetime.fromisoformat(mapeo[lei].get("probado", "2000-01-01T00:00:00+00:00")) > timedelta(days=30))]
    log(f"Por mapear: {len(pend):,}")
    if pend:
        isins = gleif_isins(set(pend))
        map_deadline = t0 + a.minutos * 60 * 0.45

        def one(lei):
            if time.time() > map_deadline:
                return lei, None
            r = map_entity(lei, nombres.get(lei, ""), country.get(lei) or "", isins.get(lei, []))
            r["probado"] = now
            return lei, r

        with ThreadPoolExecutor(4) as ex:
            for i, (lei, r) in enumerate(ex.map(one, sorted(pend, key=lambda x: len(isins.get(x, [])) == 0))):
                if r is not None:
                    mapeo[lei] = r
                if i % 200 == 199:
                    log(f"  mapeadas {i + 1}/{len(pend)} · con ticker: {sum(1 for x in mapeo.values() if x.get('ticker')):,}")
        if time.time() > map_deadline:
            log("  (tiempo de mapeo agotado: sigue en la próxima ejecución)")
    tick = {lei: m["ticker"] for lei, m in mapeo.items() if m.get("ticker") and lei in recent}
    # un ticker, una empresa (si dos LEI dan el mismo ticker, se queda el que tiene informes más recientes)
    seen: dict[str, str] = {}
    for lei, t in sorted(tick.items(), key=lambda kv: max(f["added"] for f in filings[kv[0]])):
        seen[t] = lei
    tick = {lei: t for t, lei in seen.items()}
    log(f"Con ticker: {len(tick):,}")

    # --- hechos (descargas en paralelo, con límite de tiempo)
    todo = []
    for lei in tick:
        for f in pick3(filings[lei]):
            if f["json_url"] not in hechos:
                todo.append(f)
    log(f"Informes por descargar: {len(todo):,}")
    dl_deadline = t0 + a.minutos * 60 * 0.85
    with ThreadPoolExecutor(6) as ex:
        futs = []
        for f in todo:
            futs.append(ex.submit(lambda f=f: fetch(f) if time.time() < dl_deadline else (f["json_url"], None)))
        for k, fu in enumerate(as_completed(futs)):
            url, facts = fu.result()
            if facts is not None:
                hechos[url] = facts
            if k % 500 == 499:
                log(f"  descargados {k + 1}/{len(todo)}")

    # --- Yahoo: divisa y sector de los tickers nuevos
    new_t = [t for t in tick.values() if t not in yinfo]
    yinfo.update(yahoo_meta(new_t, t0 + a.minutos * 60 * 0.95))

    # --- filas del screener + notas
    from notas_financieras import score_company
    rows, uni = [], []
    for lei, t in tick.items():
        fl = pick3(filings[lei])
        reps = [(f, hechos[f["json_url"]]) for f in fl if f["json_url"] in hechos]
        if not reps:
            continue
        name = esef.clean_name((yinfo.get(t) or {}).get("yname") or mapeo[lei].get("yname") or nombres.get(lei) or lei)
        cf = esef.to_companyfacts(name, lei, reps)
        try:
            fin = F.build(cf, t, n_years=10)
        except Exception as e:  # noqa: BLE001
            log(f"  ⚠ {t}: {e}")
            continue
        sfx = t.rsplit(".", 1)[1]
        m = {"ticker": t, "name": name, "lei": lei, "exchange": esef.YAHOO_SUFFIXES.get(sfx, sfx),
             "country": country.get(lei), "currency": (yinfo.get(t) or {}).get("currency"), "isin": mapeo[lei].get("isin")}
        row = screener.row_from_financials(fin, m)
        if not row:
            continue
        try:
            nota = score_company(cf, t) or {}
        except Exception:  # noqa: BLE001
            nota = {}
        for c in screener.NOTA_COLS:
            row[c] = nota.get(c)
        rows.append(row)
        uni.append({k: m[k] for k in ("ticker", "lei", "name", "country", "exchange", "currency", "isin")})
    base = pd.DataFrame(rows)
    log(f"Filas del screener: {len(base):,}")

    # --- precios y divisas
    px = last_prices(sorted(base["Ticker"])) if not base.empty else {}
    fx = fx_rates({(yinfo.get(t) or {}).get("currency") or "" for t in base["Ticker"]} | set(base.get("Divisa", pd.Series(dtype=str)).dropna()))
    mk = []
    for r in rows:
        t = r["Ticker"]
        qc = (yinfo.get(t) or {}).get("currency") or r["Divisa"]
        mk.append({"Ticker": t, "Precio": px.get(t), "_mcap_nq": None, "Sector": (yinfo.get(t) or {}).get("sector") or "—",
                   "Industria": (yinfo.get(t) or {}).get("industry") or "—",
                   "País": esef.COUNTRY_NAMES.get(country.get(r["LEI"]) or "", country.get(r["LEI"]) or "—"),
                   "_fx_q": fx.get(qc), "_fx_r": fx.get(r["Divisa"]), "Divisa cotización": qc})
    mkdf = pd.DataFrame(mk)

    # --- salida
    if not base.empty:
        base.to_parquet(out / "europa_base.parquet")
        mkdf.to_parquet(out / "europa_market.parquet")
        meta["base"] = meta["market"] = now
    else:  # algo ha fallado: se conserva lo publicado
        for name in ("europa_base.parquet", "europa_market.parquet"):
            raw = remoto.public_file(name, branch=BR, timeout=120)
            if raw:
                (out / name).write_bytes(raw)
    (out / "europa_universo.json").write_text(json.dumps(uni, ensure_ascii=False))
    (out / "europa_mapeo.json").write_text(json.dumps(mapeo, ensure_ascii=False))
    (out / "europa_yahoo.json").write_text(json.dumps(yinfo, ensure_ascii=False))
    (out / "europa_nombres.json").write_text(json.dumps(nombres, ensure_ascii=False))
    (out / "europa_hechos.json.gz").write_bytes(gzip.compress(json.dumps(hechos).encode("utf-8")))
    meta.update({"empresas": len(base), "mapeadas": len(tick), "informes": len(hechos), "generado": now,
                 "pendientes_mapeo": sum(1 for lei in recent if lei not in mapeo),
                 "pendientes_informes": sum(1 for lei in tick for f in pick3(filings[lei]) if f["json_url"] not in hechos)})
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    log(meta, f"· {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
