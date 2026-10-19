"""Datos preparados cada noche por GitHub Actions, para que la app arranque rápido aunque se reinicie.

- Screener (datos públicos): rama «datos» del repo de la app → screener_base.parquet, screener_market.parquet, meta.json.
  Se leen sin token desde raw.githubusercontent.com.
- Fichas (tus empresas: analizadas, en listas o en cartera): rama «fichas» de tu repo privado de datos →
  facts_<CIK>.json.gz, subs_<CIK>.json.gz, prices_<TICKER>.csv.gz e index.json. Se leen con tu GITHUB_TOKEN.

Si algo falla (sin red, rama aún no creada…), la app sigue como antes: descarga de la SEC / Yahoo.
"""
from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from . import storage

PUBLIC_BRANCH = "datos"
FICHAS_BRANCH = "fichas"


def _public_repo() -> str:
    return storage._secret("DATOS_PUBLICOS_REPO") or "jesusvicens/screener"


def _age_h(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return 1e9


# ---------------------------------------------------------------- screener (público)
def public_file(name: str, timeout: int = 60) -> bytes | None:
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{_public_repo()}/{PUBLIC_BRANCH}/{name}", timeout=timeout)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


_meta_cache: dict = {"t": 0.0, "v": None}


def public_meta() -> dict:
    if time.time() - _meta_cache["t"] < 600 and _meta_cache["v"] is not None:
        return _meta_cache["v"]
    raw = public_file("meta.json", timeout=15)
    v = json.loads(raw) if raw else {}
    _meta_cache.update(t=time.time(), v=v)
    return v


def _write_pickle_from_parquet(raw: bytes, dest, generated_iso: str | None):
    df = pd.read_parquet(io.BytesIO(raw))
    df.to_pickle(dest)
    if generated_iso:  # la antigüedad del fichero local = la del dato, no la de la descarga
        try:
            ts = datetime.fromisoformat(generated_iso.replace("Z", "+00:00")).timestamp()
            os.utime(dest, (ts, ts))
        except ValueError:
            pass
    return df


def sync_screener(base_file, market_file, max_base_age_days: float = 7, max_market_age_h: float = 24) -> dict:
    """Trae del repo los datos del screener si son más nuevos que los locales. Devuelve qué se ha actualizado."""
    done = {"base": False, "market": False}
    meta = public_meta()
    if not meta:
        return done
    now = time.time()
    local_base_age = (now - base_file.stat().st_mtime) / 86400 if base_file.exists() else 1e9
    if _age_h(meta.get("base")) / 24 < min(local_base_age, max_base_age_days):
        raw = public_file("screener_base.parquet")
        if raw:
            _write_pickle_from_parquet(raw, base_file, meta.get("base"))
            done["base"] = True
    local_mk_age = (now - market_file.stat().st_mtime) / 3600 if market_file.exists() else 1e9
    if _age_h(meta.get("market")) < min(local_mk_age, max_market_age_h):
        raw = public_file("screener_market.parquet")
        if raw:
            _write_pickle_from_parquet(raw, market_file, meta.get("market"))
            done["market"] = True
    return done


# ---------------------------------------------------------------- fichas (privado)
_idx_cache: dict = {"t": 0.0, "v": None}


def private_file(name: str, timeout: int = 30) -> bytes | None:
    if storage.backend() != "github":
        return None
    try:
        r = requests.get(f"https://api.github.com/repos/{storage._secret('GITHUB_REPO')}/contents/{name}",
                         params={"ref": FICHAS_BRANCH}, timeout=timeout,
                         headers={"Authorization": f"Bearer {storage._secret('GITHUB_TOKEN')}", "Accept": "application/vnd.github.raw"})
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


def fichas_index() -> dict:
    if time.time() - _idx_cache["t"] < 600 and _idx_cache["v"] is not None:
        return _idx_cache["v"]
    raw = private_file("index.json", timeout=15)
    try:
        v = json.loads(raw) if raw else {}
    except ValueError:
        v = {}
    _idx_cache.update(t=time.time(), v=v)
    return v


def ficha_file(name: str, max_age_h: float = 36) -> bytes | None:
    """Un fichero de la rama «fichas» si existe y se generó hace menos de max_age_h horas."""
    idx = fichas_index()
    if name not in (idx.get("files") or {}) or _age_h(idx.get("generado")) > max_age_h:
        return None
    return private_file(name)


def ficha_prices(ticker: str) -> pd.Series | None:
    raw = ficha_file(f"prices_{ticker.upper()}.csv.gz")
    if not raw:
        return None
    try:
        df = pd.read_csv(io.BytesIO(raw), compression="gzip", parse_dates=["Date"]).set_index("Date")
        s = df["Close"].dropna()
        return s if not s.empty else None
    except Exception:  # noqa: BLE001
        return None
