"""Búsqueda de texto completo en los documentos de una empresa en la SEC (EDGAR full-text search, desde 2001).

La API devuelve qué documentos contienen el texto; los fragmentos con la palabra resaltada se sacan
leyendo cada documento (solo los primeros resultados, con caché).
"""
from __future__ import annotations

import gzip
import hashlib
import html
import re
import time
import urllib.parse

from . import sec

FORMS = {"10-K": "10-K", "10-Q": "10-Q", "8-K": "8-K", "Junta (DEF 14A)": "DEF 14A", "20-F": "20-F"}


def search(cik: int, query: str, forms: list[str] | None = None, start: str | None = None) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    params = {"q": f'"{q}"' if " " in q and not q.startswith('"') else q, "ciks": f"{int(cik):010d}"}
    if forms:
        params["forms"] = ",".join(forms)
    if start:
        params.update(dateRange="custom", startdt=start, enddt=time.strftime("%Y-%m-%d"))
    r = sec._get("https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)).json()
    out = []
    for h in r.get("hits", {}).get("hits", []):
        s = h["_source"]
        adsh, fname = h["_id"].split(":", 1)
        out.append({"Fecha": s.get("file_date"), "Tipo": s.get("form") or s.get("file_type"), "Periodo": s.get("period_ending"),
                    "Documento": s.get("file_description") or fname,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fname}"})
    return sorted(out, key=lambda x: x["Fecha"] or "", reverse=True)


def _text(url: str) -> str:
    path = sec.CACHE_DIR / f"doc_{hashlib.sha1(url.encode()).hexdigest()[:16]}.txt.gz"
    if path.exists():
        return gzip.open(path, "rt", encoding="utf-8").read()
    raw = sec._get(url).text
    raw = re.sub(r"(?is)<(script|style|ix:header).*?</\1>", " ", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"\s+", " ", txt)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(txt)
    return txt


def snippets(url: str, query: str, n: int = 3, width: int = 220) -> list[str]:
    """Hasta n fragmentos con el texto buscado resaltado en **negrita**."""
    try:
        txt = _text(url)
    except Exception:  # noqa: BLE001
        return []
    q = query.strip().strip('"')
    out = []
    for m in re.finditer(re.escape(q), txt, flags=re.I):
        a, b = max(0, m.start() - width), min(len(txt), m.end() + width)
        frag = txt[a:b]
        frag = re.sub(re.escape(q), lambda x: f"**{x.group(0)}**", frag, flags=re.I)
        out.append(("…" if a else "") + frag.strip() + ("…" if b < len(txt) else ""))
        if len(out) >= n:
            break
    return out


def count(url: str, query: str) -> int:
    try:
        return len(re.findall(re.escape(query.strip().strip('"')), _text(url), flags=re.I))
    except Exception:  # noqa: BLE001
        return 0
