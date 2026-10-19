"""Guarda cada noche las fichas de TUS empresas (lo ejecuta GitHub Actions en tu repo privado de datos).

Empresas: las que tienes analizadas (data/analisis/<TICKER>.json), las de tus listas (_LISTAS) y las de tu
cartera (_CARTERA). Para cada una descarga de la SEC sus datos XBRL (facts) y su lista de presentaciones
(subs), y su cotización diaria, y lo escribe en --out con los mismos nombres que usa la caché de la app.

Uso: python scripts/fichas.py --datos ruta/a/terminal-datos/data/analisis --out out
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal import prices, sec  # noqa: E402


def tickers_from(datos: Path) -> list[str]:
    ts: set[str] = set()
    for p in datos.glob("*.json"):
        if not p.name.startswith("_"):
            ts.add(p.stem.upper())
    try:
        ls = json.loads((datos / "_LISTAS.json").read_text("utf-8"))
        ts |= {t.upper() for t in (ls.get("empresas") or {})}
    except (OSError, ValueError):
        pass
    try:
        ca = json.loads((datos / "_CARTERA.json").read_text("utf-8"))
        ts |= {str(m.get("Ticker") or m.get("ticker") or "").upper() for m in (ca.get("movimientos") or [])}
    except (OSError, ValueError):
        pass
    return sorted(t for t in ts if t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files, errs = {}, []
    tickers = tickers_from(Path(a.datos))
    print(f"{len(tickers)} empresas")
    for t in tickers:
        try:
            meta = sec.find(t)
            if not meta:
                errs.append(f"{t}: no está en el registro de la SEC")
                continue
            cik = int(meta["cik"])
            sec.company_facts(cik, max_age_h=0)
            sec.submissions(cik, max_age_h=0)
            for name in (f"facts_{cik:010d}.json.gz", f"subs_{cik:010d}.json.gz"):
                shutil.copy(sec.CACHE_DIR / name, out / name)
                files[name] = t
            h = prices.history(t, years=17)
            if not h.empty:
                name = f"prices_{t}.csv.gz"
                with gzip.open(out / name, "wt") as f:
                    h.rename("Close").rename_axis("Date").to_csv(f)
                files[name] = t
            print(f"  {t} ok ({len(h)} cotizaciones)")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{t}: {e}")
    idx = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files, "errores": errs}
    (out / "index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    print(f"{len(files)} ficheros · {len(errs)} errores")
    for e in errs:
        print("  ⚠", e)


if __name__ == "__main__":
    main()
