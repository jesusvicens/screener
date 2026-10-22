"""Empresas cotizadas europeas: cuentas anuales en formato ESEF (XBRL obligatorio en la UE desde 2020).

Fuente gratuita: filings.xbrl.org (repositorio público de XBRL International). Cada informe anual trae el
ejercicio y el anterior en normas IFRS; aquí se convierten al mismo formato que los «companyfacts» de la SEC
para que el resto de la terminal (estados, ROIC, bandas, modelo de BPA…) funcione igual que con las americanas.

Identificador de cada empresa: su LEI. En la terminal se usa su ticker de Yahoo (p. ej. RMS.PA para Hermès),
que es el que da el precio; la correspondencia LEI ↔ ticker vive en el universo europeo (ver `universe`).
"""
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from .sec import CACHE_DIR

BASE = "https://filings.xbrl.org"
UA = {"User-Agent": "Terminal personal de analisis (uso propio)"}

# Sufijos de Yahoo para las bolsas europeas: identifican un ticker como europeo.
YAHOO_SUFFIXES = {
    "PA": "Euronext París", "AS": "Euronext Ámsterdam", "BR": "Euronext Bruselas", "LS": "Euronext Lisboa",
    "IR": "Euronext Dublín", "OL": "Oslo", "MC": "Madrid", "MI": "Milán", "DE": "Xetra", "F": "Fráncfort",
    "VI": "Viena", "ST": "Estocolmo", "CO": "Copenhague", "HE": "Helsinki", "WA": "Varsovia", "AT": "Atenas",
    "PR": "Praga", "BD": "Budapest", "L": "Londres", "SW": "Suiza", "IC": "Islandia", "TL": "Tallin",
    "VS": "Vilna", "RG": "Riga",
}

COUNTRY_NAMES = {
    "FR": "Francia", "DE": "Alemania", "ES": "España", "IT": "Italia", "NL": "Países Bajos", "BE": "Bélgica",
    "PT": "Portugal", "IE": "Irlanda", "AT": "Austria", "FI": "Finlandia", "SE": "Suecia", "DK": "Dinamarca",
    "NO": "Noruega", "PL": "Polonia", "GR": "Grecia", "LU": "Luxemburgo", "CZ": "Chequia", "HU": "Hungría",
    "GB": "Reino Unido", "UK": "Reino Unido", "CH": "Suiza", "IS": "Islandia", "EE": "Estonia", "LT": "Lituania",
    "LV": "Letonia", "SI": "Eslovenia", "SK": "Eslovaquia", "HR": "Croacia", "RO": "Rumanía", "BG": "Bulgaria",
    "CY": "Chipre", "MT": "Malta",
}


_LEGAL = re.compile(r"[,\s]+(soci[ée]t[ée] en commandite par actions|soci[ée]t[ée] europ[ée]enne|soci[ée]t[ée] anonyme|"
                    r"s\.?\s?p\.?\s?a\.?|s\.?a\.?|se|n\.?v\.?|plc|ag|asa|ab \(publ\)|ab|oyj|a/s|sca|s\.c\.a\.|kgaa|"
                    r"& co\.? kgaa|spółka akcyjna)\.?$", re.I)


def clean_name(name: str) -> str:
    """Quita la forma jurídica del final: «Hermès International Société en commandite par actions» → «Hermès International»."""
    n = (name or "").strip()
    for _ in range(3):
        m = _LEGAL.sub("", n).strip(" ,-")
        if m == n or not m:
            break
        n = m
    return n


def is_european(ticker: str) -> bool:
    t = (ticker or "").upper()
    return "." in t and t.rsplit(".", 1)[1] in YAHOO_SUFFIXES


def _get(url: str, timeout: int = 90) -> requests.Response:
    for i in range(3):
        try:
            r = requests.get(url if url.startswith("http") else BASE + url, headers=UA, timeout=timeout)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(2 + 3 * i)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == 2:
                raise
            time.sleep(2 + 3 * i)
    r.raise_for_status()
    return r


def _api(path: str, **params) -> dict:
    return _get(requests.Request("GET", BASE + path, params=params).prepare().url).json()


# ---------------------------------------------------------------- búsqueda y lista de informes
def search_entities(text: str, limit: int = 20) -> list[dict]:
    """Empresas con informes ESEF cuyo nombre contiene el texto: [{lei, name}]."""
    flt = json.dumps([{"name": "name", "op": "ilike", "val": f"%{text}%"}])
    d = _api("/api/entities", filter=flt, **{"page[size]": limit})
    return [{"lei": e["attributes"]["identifier"], "name": e["attributes"]["name"]} for e in d.get("data", [])]


def entity_filings(lei: str) -> list[dict]:
    d = _api(f"/api/entities/{lei}/filings", **{"page[size]": 100})
    out = []
    for f in d.get("data", []):
        a = f["attributes"]
        if not a.get("json_url"):
            continue
        out.append({"id": f["id"], "period_end": a.get("period_end"), "country": a.get("country"),
                    "added": a.get("date_added") or "", "published": a.get("published") or "",
                    "json_url": a["json_url"], "viewer_url": a.get("viewer_url"), "report_url": a.get("report_url"),
                    "package_url": a.get("package_url"), "errors": a.get("error_count") or 0})
    return out


# ---------------------------------------------------------------- xBRL-JSON → hechos compactos
def _end(s: str) -> str:
    """En xBRL-JSON las fechas de cierre son exclusivas («2026-01-01T00:00:00» = cierre el 31-12-2025)."""
    d = date.fromisoformat(s[:10])
    if len(s) > 10 and s[11:19] == "00:00:00":
        d -= timedelta(days=1)
    return d.isoformat()


def _unit(u: str | None) -> str | None:
    if not u:
        return None
    parts = [p.split(":")[-1] for p in u.split("/")]
    return "/".join(parts)


def compact(doc: dict) -> list[list]:
    """Solo los hechos sin dimensiones (las cifras de los estados): [concepto, inicio|None, fin, unidad, valor, decimales]."""
    out = []
    for v in (doc.get("facts") or {}).values():
        dm = v.get("dimensions") or {}
        if set(dm) - {"concept", "entity", "period", "unit", "language"}:
            continue
        val, concept, per = v.get("value"), dm.get("concept"), dm.get("period")
        if val is None or not concept or not per:
            continue
        try:
            x = float(val)
        except (TypeError, ValueError):
            continue
        if "/" in per:
            a, b = per.split("/")
            start, end = date.fromisoformat(a[:10]).isoformat(), _end(b)
        else:
            start, end = None, _end(per)
        out.append([concept, start, end, _unit(dm.get("unit")), x, v.get("decimals")])
    return out


def filing_facts(f: dict) -> list[list]:
    """Hechos de un informe (se guardan para siempre: un informe publicado no cambia)."""
    key = re.sub(r"[^A-Za-z0-9]+", "_", f["json_url"]).strip("_")[-150:]
    path = CACHE_DIR / f"esef_{key}.json.gz"
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    facts = compact(_get(f["json_url"], timeout=180).json())
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(facts, fh)
    return facts


def annual_only(filings: list[dict]) -> list[dict]:
    """Solo los informes anuales: algunas empresas (p. ej. Novo Nordisk) también suben los trimestrales.
    El mes de cierre del ejercicio es el que más se repite; en caso de empate, diciembre."""
    from collections import Counter
    months = Counter((f["period_end"] or "")[5:7] for f in filings if f.get("period_end"))
    if len(months) <= 1:
        return filings
    top = max(months.values())
    cands = [m for m, c in months.items() if c == top]
    fye = "12" if "12" in cands else sorted(cands)[-1]
    return [f for f in filings if (f["period_end"] or "")[5:7] == fye]


def pick_filings(filings: list[dict], max_reports: int = 8) -> list[dict]:
    """Un informe por ejercicio: el último añadido (corrige reenvíos y versiones por idioma)."""
    by: dict[str, dict] = {}
    for f in annual_only(filings):
        k = f["period_end"] or ""
        if k not in by or f["added"] > by[k]["added"]:
            by[k] = f
    return [by[k] for k in sorted(by, reverse=True)[:max_reports]]


# Conceptos propios de la empresa (extensiones) que equivalen a uno estándar de NIIF: solo se usan si el
# informe no trae el estándar (p. ej. Hermès declara las amortizaciones con una etiqueta propia).
ALIASES = [
    (re.compile(r"^(Depreciation|Amortisation|Amortization)", re.I), "DepreciationAndAmortisationExpense", "flow"),
    (re.compile(r"Average.*Shares.*Dilut|Dilut.*Average.*Shares", re.I), "AdjustedWeightedAverageShares", "sh"),
    (re.compile(r"Average.*(Number|Shares)", re.I), "WeightedAverageShares", "sh"),
]


def _with_aliases(facts: list[list]) -> list[list]:
    have = {c.split(":", 1)[-1] for c, *_ in facts if c.startswith("ifrs")}
    groups: dict[tuple, dict[str, list]] = {}  # (estándar, inicio, fin, unidad) -> {concepto: hecho}
    for c, start, end, unit, val, dec in facts:
        pre, _, tag = c.partition(":")
        if pre.startswith("ifrs"):
            continue
        for rx, std, kind in ALIASES:
            if std in have:
                continue
            ok = (kind == "flow" and start and unit and "/" not in unit and unit != "shares") or (kind == "sh" and unit == "shares" and start)
            if ok and rx.search(tag):
                groups.setdefault((std, start, end, unit), {})[tag] = [val, dec]
                break
    extra = []
    for (std, start, end, unit), items in groups.items():
        if std.endswith("Shares"):
            val, dec = next(iter(items.values()))
        else:
            # un total («…And…») si lo hay; si no, la suma de las partes (inmovilizado + derechos de uso…)
            totals = {k: v for k, v in items.items() if "And" in k}
            pick = totals or items
            val = max(abs(v[0]) for v in pick.values()) if totals else sum(abs(v[0]) for v in pick.values())
            dec = next(iter(pick.values()))[1]
        extra.append([f"ifrs-full:{std}", start, end, unit, abs(val), dec])
    return facts + extra


def to_companyfacts(name: str, lei: str, reports: list[tuple[dict, list[list]]]) -> dict:
    """Formato «companyfacts» de la SEC (lo que entiende financials.build)."""
    tax: dict[str, dict] = {}
    for f, facts in reports:
        filed = (f.get("published") or f.get("added") or "")[:10]
        for concept, start, end, unit, val, _dec in _with_aliases(facts):
            pre, _, tag = concept.partition(":")
            pre = "ifrs-full" if pre in ("ifrs-full", "ifrs") else pre
            node = tax.setdefault(pre, {}).setdefault(tag, {"units": {}})
            row = {"end": end, "val": val, "form": "ESEF", "filed": filed}
            if start:
                row["start"] = start
            node["units"].setdefault(unit or "pure", []).append(row)
    return {"entityName": name, "cik": 0, "lei": lei, "facts": tax}


def _cache_json(name: str, max_age_h: float):
    p = CACHE_DIR / f"{name}.json.gz"
    if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _cache_put(name: str, data) -> None:
    with gzip.open(CACHE_DIR / f"{name}.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(data, fh)


def company_facts(lei: str, name: str = "", max_age_h: float = 24) -> dict:
    hit = _cache_json(f"esef_cf_{lei}", max_age_h)
    if hit:
        return hit
    filings = pick_filings(entity_filings(lei))
    reports = []
    for f in filings:
        try:
            reports.append((f, filing_facts(f)))
        except Exception:  # noqa: BLE001  (un informe roto no impide ver los demás)
            continue
    cf = to_companyfacts(name or lei, lei, reports)
    cf["informes"] = filings
    _cache_put(f"esef_cf_{lei}", cf)
    return cf


# ---------------------------------------------------------------- universo europeo (LEI ↔ ticker de Yahoo)
UNIVERSE_FILE = "europa_universo.json"


def universe() -> list[dict]:
    """[{ticker, lei, name, country, exchange, currency, isin}] — lo prepara cada semana el proceso de datos."""
    hit = _cache_json("europa_universo", 24)
    if hit is not None:
        return hit
    data = []
    try:
        from . import remoto
        raw = remoto.public_file(UNIVERSE_FILE)
        if raw:
            data = json.loads(raw)
    except Exception:  # noqa: BLE001
        data = []
    local = Path(__file__).resolve().parent.parent / "data" / UNIVERSE_FILE
    if not data and local.exists():
        data = json.loads(local.read_text("utf-8"))
    data = data + [x for x in _extra() if x["ticker"] not in {d["ticker"] for d in data}]
    if data:
        _cache_put("europa_universo", data)
    return data


def _extra() -> list[dict]:
    """Empresas añadidas a mano (por si el universo aún no las tiene)."""
    return [
        {"ticker": "RMS.PA", "lei": "969500Y4IJGHJE2MTJ13", "name": "Hermès International", "country": "FR",
         "exchange": "Euronext París", "currency": "EUR", "isin": "FR0000052292"},
    ]


def find(ticker: str) -> dict | None:
    t = (ticker or "").strip().upper()
    for x in universe():
        if x["ticker"].upper() == t:
            return {**x, "cik": 0, "region": "EU", "title": x["name"]}
    return None
