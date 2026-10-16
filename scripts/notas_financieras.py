"""Calcula el examen financiero (21 preguntas, 4 bloques) para TODAS las empresas con ticker.

Usa el archivo masivo de la SEC (companyfacts.zip, ~1,4 GB, se actualiza cada noche) para no tener
que hacer 10.000 descargas. Lo ejecuta cada semana una GitHub Action (.github/workflows/notas.yml)
y deja el resultado en data/notas_financieras.csv.gz, que el screener lee.

Uso manual:  python scripts/notas_financieras.py [ruta/companyfacts.zip]
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal import analysis as A, exam as E, financials as F, sec  # noqa: E402

OUT = ROOT / "data" / "notas_financieras.csv.gz"
URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"


def download(dest: Path) -> Path:
    ua = os.environ.get("SEC_USER_AGENT", sec.DEFAULT_UA)
    with requests.get(URL, headers={"User-Agent": ua}, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest


def score_company(facts: dict, ticker: str) -> dict | None:
    fin = F.build(facts, ticker, n_years=10)
    if len(fin.years) < 4 or fin.get("revenue", fin.years[-1]) is None:
        return None
    stats = A.history_stats(fin)
    sug = E.suggestions(fin, stats)
    sc = E.score({k: v[0] for k, v in sug.items()})
    b = sc["blocks"]
    row = {"Ticker": ticker, "Nota financiera": round(sc["financiera"], 2),
           "Nota PyG": None if b["PyG"]["nota"] is None else round(b["PyG"]["nota"], 2),
           "Nota Balance": None if b["Balance"]["nota"] is None else round(b["Balance"]["nota"], 2),
           "Nota Cash Flow": None if b["Cash Flow"]["nota"] is None else round(b["Cash Flow"]["nota"], 2),
           "Nota Asignación de capital": None if b["Asignación de capital"]["nota"] is None else round(b["Asignación de capital"]["nota"], 2),
           "Preguntas no aplicables": sum(b[x]["na"] for x in E.FINANCIAL_BLOCKS),
           "Fase": stats.get("phase"), "Último ejercicio": fin.years[-1]}
    for qid, (pts, _why) in sug.items():
        row[qid] = pts
    return row


def main(zip_path: str | None = None):
    t0 = time.time()
    zp = Path(zip_path) if zip_path else ROOT / "data" / "cache" / "companyfacts.zip"
    if not zp.exists():
        print("Descargando companyfacts.zip de la SEC…", flush=True)
        zp.parent.mkdir(parents=True, exist_ok=True)
        download(zp)
    uni = sec.universe()
    by_cik: dict[int, str] = {}
    for u in uni:
        by_cik.setdefault(int(u["cik"]), u["ticker"])
    rows, errors = [], 0
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if n.startswith("CIK") and n.endswith(".json")]
        for i, name in enumerate(names):
            cik = int(name[3:13])
            tk = by_cik.get(cik)
            if not tk:
                continue
            try:
                facts = json.loads(z.read(name))
                r = score_company(facts, tk)
                if r:
                    r["CIK"] = cik
                    rows.append(r)
            except Exception:  # noqa: BLE001
                errors += 1
            if i % 1000 == 0:
                print(f"{i}/{len(names)} · {len(rows)} empresas puntuadas · {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        df.to_csv(fh, index=False)
    print(f"Listo: {len(df)} empresas, {errors} errores, {time.time() - t0:.0f}s → {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
