from __future__ import annotations

import math
import numbers

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Paleta clara estilo macrotrends: fondo blanco, barra superior azul marino, gráficos en azul acero.
AMBER, GREEN, RED, BLUE, MUTED, TEXT, PANEL, BG, GRID = "#e07b24", "#2e8b57", "#c0392b", "#2f6db5", "#6b7280", "#1f2937", "#ffffff", "#ffffff", "#e5e7eb"
NAVY, HEAD, ZEBRA, LINK = "#1b2a41", "#f3f5f8", "#fafbfc", "#1a5fb4"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Roboto+Mono:wght@400;500&display=swap');
html, body, [class*="css"], .stMarkdown, p, li, label, input, textarea {{ font-family: 'Source Sans 3', Arial, sans-serif; color: {TEXT}; }}
[data-testid="stMetricValue"], .mono {{ font-family: 'Roboto Mono', monospace !important; }}
.stApp {{ background: {BG}; }}
header[data-testid="stHeader"] {{ background: {NAVY}; }}
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span, header[data-testid="stHeader"] p,
header[data-testid="stHeader"] button {{ color: #e8eef7 !important; }}
header[data-testid="stHeader"] [aria-current="page"], header[data-testid="stHeader"] a[aria-current] {{ background: rgba(255,255,255,.14) !important; border-radius: 4px; }}
.block-container {{ padding-top: 4.2rem; padding-bottom: 3rem; max-width: 1400px; }}
h1 {{ font-size: 1.7rem !important; font-weight: 700 !important; color: {TEXT} !important; letter-spacing: 0; }}
h2 {{ font-size: 1.12rem !important; font-weight: 700 !important; color: {NAVY} !important; border-bottom: 2px solid {BLUE};
      padding-bottom: .25rem !important; margin-top: 1.4rem !important; }}
h3 {{ font-size: 1rem !important; font-weight: 600 !important; color: {TEXT} !important; }}
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {GRID}; border-top: 3px solid {BLUE}; border-radius: 3px; padding: .5rem .8rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .78rem !important; font-weight: 600; }}
[data-testid="stMetricValue"] {{ font-size: 1.3rem !important; color: {TEXT}; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid {GRID}; background: {HEAD}; }}
.stTabs [data-baseweb="tab"] {{ font-size: .92rem; font-weight: 600; padding: .55rem 1rem; color: {LINK}; }}
.stTabs [aria-selected="true"] {{ color: {TEXT} !important; background: {PANEL}; border: 1px solid {GRID}; border-bottom: 1px solid {PANEL}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {GRID}; border-radius: 2px; }}
.tick {{ font-family: 'Roboto Mono', monospace; background: {BLUE}; color: #fff; padding: .08rem .5rem; border-radius: 3px; font-weight: 500; margin-right: .6rem; font-size: 1.2rem; }}
.subtle {{ color: {MUTED}; font-size: .88rem; }}
.pill {{ display:inline-block; font-size:.78rem; padding:.1rem .5rem; border-radius:3px; border:1px solid {GRID}; background:{HEAD}; color:{MUTED}; margin-right:.4rem; }}
.pill.ok {{ color:{GREEN}; border-color:{GREEN}; background:#eef8f2; }} .pill.ko {{ color:{RED}; border-color:{RED}; background:#fdf0ee; }}
.pill.am {{ color:{BLUE}; border-color:{BLUE}; background:#eef4fb; }}
.why {{ color:{MUTED}; font-size:.82rem; margin:-.6rem 0 .6rem 0; }}
a {{ color: {LINK}; }}
hr {{ border-color: {GRID} !important; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def pct(x, d=1):
    return f"{x * 100:.{d}f}%" if ok(x) and isinstance(x, (int, float)) else ("—" if not isinstance(x, str) else x)


def num(x, d=0):
    return f"{x:,.{d}f}" if ok(x) and isinstance(x, (int, float)) else ("—" if not isinstance(x, str) else x)


def mult(x, d=1):
    return f"{x:.{d}f}x" if ok(x) and isinstance(x, (int, float)) else ("—" if not isinstance(x, str) else x)


PCT_HINTS = ("%", "margen", "roe", "roic", "crecimiento", "δ", "tasa", "rentabilidad", "variación de acciones", "probabilidad",
             "riesgo de no", "payout", "cagr", "s/ b", "retenido", "seguridad", "frente al precio", "resultado del activo",
             "efecto sobre", "var. acciones", "holgura", "pérdida temporal", "peso en", "tras la caída")
MULT_HINTS = ("per", "múltiplo", "deuda neta / ebitda", "cobertura")
PS_HINTS = ("bpa", "por acción", "precio", "dividendo por", "vf", "valor", "umbral", "déficit", "exceso", "oportunidad",
            "riesgo asumido", "ponderado", "caja acumulada", "dividendos capitalizados", "e[vf]", "vc ")


def kind_of(label: str) -> str:
    l = str(label).lower()
    if l.startswith(("ponderado", "precio máximo", "umbral", "valor estimado", "precio en el año")):
        return "ps"
    if any(h in l for h in PCT_HINTS):
        return "pct"
    if any(l.startswith(h) or f" {h}" in l for h in MULT_HINTS):
        return "x"
    if any(h in l for h in PS_HINTS):
        return "ps"
    return "m"


def fmt_cell(v, kind):
    if isinstance(v, str):
        return v
    if not isinstance(v, numbers.Number):
        return "—" if v is None or v is pd.NaT else (v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v))
    v = float(v)
    if not ok(v):
        return "—"
    if kind == "int":
        return f"{v:.0f}"
    if kind == "pct":
        return pct(v)
    if kind == "x":
        return mult(v)
    if kind == "ps":
        return num(v, 2)
    return num(v, 0) if abs(v) >= 100 else num(v, 1)


def show_rows_table(df: pd.DataFrame, kinds: dict | None = None, height: int | None = None):
    """Tabla con filas = conceptos y columnas = años; cada fila con su formato."""
    kinds = kinds or {}
    out = df.copy().astype(object)
    for idx in out.index:
        k = kinds.get(idx) or kind_of(idx)
        out.loc[idx] = [fmt_cell(v, k) for v in df.loc[idx]]
    out.columns = [str(c) for c in out.columns]
    st.dataframe(out, width="stretch", height=height or min(38 + 35 * len(out), 900))


def link_key() -> str:
    """Llave para enlaces internos (abre fichas en otra pestaña sin pedir otra vez la contraseña)."""
    import hashlib
    try:
        pwd = st.secrets.get("APP_PASSWORD") or ""
    except Exception:  # noqa: BLE001
        pwd = ""
    return hashlib.sha256(f"terminal-link|{pwd}".encode()).hexdigest()[:24] if pwd else ""


def company_url(ticker: str, name: str = "") -> str:
    k = link_key()
    return f"./?ticker={ticker}" + (f"&k={k}" if k else "") + f"#{name or ticker}"


def show_cols_table(df: pd.DataFrame, height: int | None = None, kinds: dict | None = None, column_config: dict | None = None):
    """Tabla con columnas = conceptos (formato por columna)."""
    kinds = kinds or {}
    column_config = column_config or {}
    out = df.copy().astype(object)
    for c in out.columns:
        if c in column_config:
            continue
        k = kinds.get(c) or kind_of(c)
        out[c] = [fmt_cell(v, k) for v in df[c]]
    st.dataframe(out, width="stretch", height=height or min(38 + 35 * len(out), 700), column_config=column_config or None)


def kv_table(d: dict):
    rows = [(k, fmt_cell(v, kind_of(k))) for k, v in d.items()]
    st.dataframe(pd.DataFrame(rows, columns=["", "Valor"]).set_index(""), width="stretch", height=38 + 35 * len(rows))


def fig_layout(fig: go.Figure, title: str = "", h: int = 300):
    fig.update_layout(template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", height=h,
                      margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      title=dict(text=title, font=dict(size=15, family="Source Sans 3, Arial", color=TEXT)),
                      font=dict(family="Source Sans 3, Arial", size=12, color=TEXT), legend=dict(orientation="h", y=-0.15, font=dict(size=11)),
                      xaxis=dict(gridcolor="#eef0f3", type="category", linecolor="#c9ced6"), yaxis=dict(gridcolor="#e3e6eb", zerolinecolor="#c9ced6"),
                      hoverlabel=dict(bgcolor="#ffffff", font_family="Source Sans 3, Arial"))
    return fig
