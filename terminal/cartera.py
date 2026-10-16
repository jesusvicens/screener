"""Cartera: movimientos, posiciones, plusvalías FIFO en euros (IRPF) y dividendos.

Criterios fiscales que aplica (normativa española, revísalo con tu asesor):
- FIFO obligatorio para valores homogéneos (art. 37.2 LIRPF): se venden primero las acciones más antiguas.
- Valor de adquisición = precio × acciones + comisiones; valor de transmisión = precio × acciones − comisiones.
- Conversión a euros con el tipo de cambio de referencia del BCE del día de cada operación (último publicado si ese día no hubo).
- Regla de los dos meses (art. 33.5.f): si vendes con pérdidas y has comprado (o compras) acciones de la misma
  empresa en los dos meses anteriores o posteriores, la pérdida no se integra hasta que vendas esas acciones.
  Aquí se marca como aviso; no se difiere automáticamente.
- Dividendos: importe bruto y retención en origen en euros (para la deducción por doble imposición internacional).
"""
from __future__ import annotations

import csv
import io
import time
from collections import defaultdict, deque
from datetime import date, timedelta

import pandas as pd
import requests

from . import sec

TIPOS = ["Compra", "Venta", "Dividendo", "Split"]
COLUMNS = ["Fecha", "Tipo", "Ticker", "Acciones", "Precio", "Importe", "Comisión", "Retención", "Divisa", "Notas"]
FX_FILE = sec.CACHE_DIR / "ecb_fx.pkl"


# ---------------------------------------------------------------- tipos de cambio del BCE
def _load_fx() -> dict[str, pd.Series]:
    if FX_FILE.exists() and (time.time() - FX_FILE.stat().st_mtime) < 12 * 3600:
        return pd.read_pickle(FX_FILE)
    return {}


def fx_series(ccy: str) -> pd.Series:
    """Unidades de `ccy` por 1 EUR (tipo de referencia del BCE), serie diaria desde 1999."""
    ccy = (ccy or "USD").upper()
    if ccy == "EUR":
        return pd.Series(dtype=float)
    cache = _load_fx()
    if ccy in cache:
        return cache[ccy]
    url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{ccy}.EUR.SP00.A?startPeriod=1999-01-01&format=csvdata"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), usecols=["TIME_PERIOD", "OBS_VALUE"])
        s = pd.Series(df["OBS_VALUE"].values, index=pd.to_datetime(df["TIME_PERIOD"])).dropna().sort_index()
    except Exception:  # noqa: BLE001  respaldo: frankfurter (también datos del BCE)
        r = requests.get(f"https://api.frankfurter.dev/v1/1999-01-04..?from=EUR&to={ccy}", timeout=60)
        rates = r.json()["rates"]
        s = pd.Series({pd.Timestamp(d): v[ccy] for d, v in rates.items()}).sort_index()
    cache[ccy] = s
    pd.to_pickle(cache, FX_FILE)
    return s


def fx_on(ccy: str, d) -> float:
    """Tipo del BCE del día d (o el último publicado antes)."""
    if (ccy or "USD").upper() == "EUR":
        return 1.0
    s = fx_series(ccy)
    s = s[s.index <= pd.Timestamp(d)]
    return float(s.iloc[-1]) if not s.empty else float("nan")


# ---------------------------------------------------------------- movimientos
def normalize(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows or [], columns=COLUMNS)
    for c in ("Acciones", "Precio", "Importe", "Comisión", "Retención"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df["Ticker"] = df["Ticker"].fillna("").astype(str).str.upper().str.strip()
    df["Tipo"] = df["Tipo"].fillna("Compra")
    df["Divisa"] = df["Divisa"].fillna("USD").replace("", "USD").str.upper()
    df["Notas"] = df["Notas"].fillna("")
    df = df[df["Fecha"].notna() & (df["Ticker"] != "")]
    order = {"Split": 0, "Compra": 1, "Dividendo": 2, "Venta": 3}
    return df.assign(_o=df["Tipo"].map(order).fillna(9)).sort_values(["Fecha", "_o"]).drop(columns="_o").reset_index(drop=True)


def to_records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out[COLUMNS].to_dict("records")


# ---------------------------------------------------------------- FIFO
def process(rows: list[dict]) -> dict:
    df = normalize(rows)
    lots: dict[str, deque] = defaultdict(deque)   # cada lote: [acciones, coste/acción en divisa, coste/acción en EUR, fecha, divisa]
    sales, divs, warnings = [], [], []
    buys_by_ticker: dict[str, list[date]] = defaultdict(list)
    for r in df.itertuples(index=False):
        if r.Tipo == "Compra":
            buys_by_ticker[r.Ticker].append(r.Fecha.date())
    for r in df.itertuples(index=False):
        t, d, q = r.Ticker, r.Fecha.date(), float(r.Acciones)
        fx = fx_on(r.Divisa, d)
        if r.Tipo == "Split":
            f = q if q > 0 else 1.0
            for lot in lots[t]:
                lot[0] *= f
                lot[1] /= f
                lot[2] /= f
        elif r.Tipo == "Compra":
            cost_ccy = q * r.Precio + r.Comisión
            lots[t].append([q, cost_ccy / q if q else 0, cost_ccy / fx / q if q else 0, d, r.Divisa])
        elif r.Tipo == "Venta":
            remaining = q
            proceeds_ccy_ps = (q * r.Precio - r.Comisión) / q if q else 0
            while remaining > 1e-9 and lots[t]:
                lot = lots[t][0]
                take = min(lot[0], remaining)
                cost_eur = take * lot[2]
                proc_eur = take * proceeds_ccy_ps / fx
                gain = proc_eur - cost_eur
                two_m = gain < 0 and any(abs((b - d).days) <= 61 and b != lot[3] for b in buys_by_ticker[t])
                sales.append({"Ticker": t, "Fecha adquisición": lot[3], "Fecha transmisión": d, "Acciones": take,
                              "Precio compra": lot[1], "Precio venta": r.Precio, "Divisa": r.Divisa,
                              "Valor adquisición (€)": cost_eur, "Valor transmisión (€)": proc_eur, "Ganancia / pérdida (€)": gain,
                              "Ganancia en divisa": take * (proceeds_ccy_ps - lot[1]),
                              "Aviso": "Posible regla de los 2 meses" if two_m else ""})
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[t].popleft()
            if remaining > 1e-9:
                warnings.append(f"{t} {d}: vendes {remaining:g} acciones más de las que constan compradas.")
        elif r.Tipo == "Dividendo":
            gross = r.Importe if r.Importe else q * r.Precio
            divs.append({"Ticker": t, "Fecha": d, "Divisa": r.Divisa, "Bruto (divisa)": gross, "Retención (divisa)": r.Retención,
                         "Bruto (€)": gross / fx, "Retención (€)": r.Retención / fx, "Neto (€)": (gross - r.Retención) / fx})
    positions = []
    for t, q in lots.items():
        sh = sum(l[0] for l in q)
        if sh <= 1e-9:
            continue
        cost_ccy = sum(l[0] * l[1] for l in q)
        cost_eur = sum(l[0] * l[2] for l in q)
        positions.append({"Ticker": t, "Acciones": sh, "Coste medio": cost_ccy / sh, "Coste total": cost_ccy, "Coste total (€)": cost_eur,
                          "Divisa": q[0][4], "Primera compra": min(l[3] for l in q), "Lotes": len(q)})
    return {"movimientos": df, "posiciones": pd.DataFrame(positions), "ventas": pd.DataFrame(sales),
            "dividendos": pd.DataFrame(divs), "avisos": warnings}


def value_positions(pos: pd.DataFrame, prices: dict[str, float]) -> pd.DataFrame:
    if pos.empty:
        return pos
    df = pos.copy()
    today = date.today()
    df["Precio actual"] = df["Ticker"].map(lambda t: prices.get(t) or prices.get(t.replace(".", "-")))
    df["Valor"] = df["Acciones"] * df["Precio actual"]
    df["Valor (€)"] = [v / fx_on(c, today) if pd.notna(v) else None for v, c in zip(df["Valor"], df["Divisa"])]
    df["Plusvalía latente"] = df["Valor"] - df["Coste total"]
    df["Plusvalía latente (€)"] = df["Valor (€)"] - df["Coste total (€)"]
    df["Rentabilidad"] = df["Valor"] / df["Coste total"] - 1
    df["Rentabilidad en €"] = df["Valor (€)"] / df["Coste total (€)"] - 1
    tot = df["Valor (€)"].sum()
    df["Peso"] = df["Valor (€)"] / tot if tot else None
    return df


def tax_year(res: dict, year: int) -> dict:
    s, d = res["ventas"], res["dividendos"]
    sy = s[pd.to_datetime(s["Fecha transmisión"]).dt.year == year] if not s.empty else s
    dy = d[pd.to_datetime(d["Fecha"]).dt.year == year] if not d.empty else d
    g = sy["Ganancia / pérdida (€)"] if not sy.empty else pd.Series(dtype=float)
    return {"ventas": sy, "dividendos": dy, "resumen": {
        "Valor de transmisión total (€)": float(sy["Valor transmisión (€)"].sum()) if not sy.empty else 0.0,
        "Valor de adquisición total (€)": float(sy["Valor adquisición (€)"].sum()) if not sy.empty else 0.0,
        "Ganancias (€)": float(g[g > 0].sum()), "Pérdidas (€)": float(g[g < 0].sum()), "Saldo neto (€)": float(g.sum()),
        "Ventas con aviso de regla de 2 meses": int((sy["Aviso"] != "").sum()) if not sy.empty else 0,
        "Dividendos brutos (€)": float(dy["Bruto (€)"].sum()) if not dy.empty else 0.0,
        "Retenciones en origen (€)": float(dy["Retención (€)"].sum()) if not dy.empty else 0.0,
    }}


# ---------------------------------------------------------------- importar de Interactive Brokers
def parse_ibkr(text: str) -> tuple[list[dict], list[str]]:
    """Lee el «Activity Statement» en CSV de IBKR (secciones Trades, Dividends y Withholding Tax).
    Cada sección trae su propia fila Header; se leen las columnas por nombre."""
    rows, notes = [], []
    headers: dict[str, list[str]] = {}
    divs: dict[tuple, dict] = {}
    for rec in csv.reader(io.StringIO(text)):
        if len(rec) < 3:
            continue
        sec_name, kind = rec[0], rec[1]
        if kind == "Header":
            headers[sec_name] = rec
            continue
        if kind != "Data" or sec_name not in headers:
            continue
        h = dict(zip(headers[sec_name], rec))
        if sec_name == "Trades":
            if h.get("DataDiscriminator", "Order") not in ("Order", "Trade") or "Stock" not in h.get("Asset Category", "Stocks"):
                continue
            try:
                q = float(h["Quantity"].replace(",", ""))
                px = float(h["T. Price"].replace(",", ""))
                comm = abs(float((h.get("Comm/Fee") or h.get("Comm in USD") or "0").replace(",", "")))
            except (KeyError, ValueError):
                continue
            d = h.get("Date/Time", "")[:10]
            rows.append({"Fecha": d, "Tipo": "Compra" if q > 0 else "Venta", "Ticker": h.get("Symbol", "").split()[0],
                         "Acciones": abs(q), "Precio": px, "Importe": 0.0, "Comisión": comm, "Retención": 0.0,
                         "Divisa": h.get("Currency", "USD"), "Notas": "IBKR"})
        elif sec_name in ("Dividends", "Withholding Tax"):
            desc, amt, ccy, d = h.get("Description", ""), h.get("Amount", "0"), h.get("Currency", "USD"), h.get("Date", "")
            if not d or ccy.startswith("Total"):
                continue
            tk = desc.split("(")[0].strip().split()[0] if desc else ""
            try:
                a = float(amt.replace(",", ""))
            except ValueError:
                continue
            key = (d, tk, ccy)
            dv = divs.setdefault(key, {"Fecha": d, "Tipo": "Dividendo", "Ticker": tk, "Acciones": 0.0, "Precio": 0.0, "Importe": 0.0,
                                       "Comisión": 0.0, "Retención": 0.0, "Divisa": ccy, "Notas": "IBKR"})
            if sec_name == "Dividends":
                dv["Importe"] += a
            else:
                dv["Retención"] += -a
    rows += [v for v in divs.values() if v["Importe"] or v["Retención"]]
    if not rows:
        notes.append("No he encontrado operaciones. Exporta desde IBKR: Informes → Extractos → Actividad → formato CSV.")
    return rows, notes


def demo_rows() -> list[dict]:
    return [{"Fecha": (date.today() - timedelta(days=200)).isoformat(), "Tipo": "Compra", "Ticker": "ADBE", "Acciones": 10, "Precio": 350.0,
             "Importe": 0.0, "Comisión": 1.0, "Retención": 0.0, "Divisa": "USD", "Notas": "Ejemplo: bórralo"}]
