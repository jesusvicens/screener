"""Prepara los datos del screener para la app (lo ejecuta GitHub Actions cada noche).

- Precios, capitalización y sector de todas las acciones (screener público de Nasdaq): cada día.
- Fundamentales de la SEC para el screener: si los publicados tienen más de 6 días (o con --forzar).
Escribe en --out: screener_market.parquet, screener_base.parquet y meta.json (fechas de generación).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal import remoto, screener  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--forzar", action="store_true", help="Recalcula los fundamentales aunque sean recientes")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev = remoto.public_meta()
    meta = {"market": None, "base": prev.get("base")}

    mk = screener.refresh_market(progress=lambda p, m: print(f"  {m}"))
    if mk is None or mk.empty:
        raw = remoto.public_file("screener_market.parquet")
        if raw:
            (out / "screener_market.parquet").write_bytes(raw)
            meta["market"] = prev.get("market")
        print("⚠ Nasdaq no ha respondido: se conservan los precios anteriores.")
    else:
        mk.to_parquet(out / "screener_market.parquet")
        meta["market"] = now
        print(f"Precios: {len(mk):,} acciones")

    base_age_d = remoto._age_h(prev.get("base")) / 24
    raw = None if (a.forzar or base_age_d > 6) else remoto.public_file("screener_base.parquet")
    if raw:
        (out / "screener_base.parquet").write_bytes(raw)
        print(f"Fundamentales: se conservan los de hace {base_age_d:.1f} días")
    else:
        base = screener.build_base(progress=lambda p, m: None)
        base.to_parquet(out / "screener_base.parquet")
        meta["base"] = now
        print(f"Fundamentales: {len(base):,} empresas recalculadas")
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(meta)


if __name__ == "__main__":
    main()
