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


def es(s: str) -> str:
    """Formato español: punto para los miles y coma para los decimales (1.234,5)."""
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _isnum(x) -> bool:
    return isinstance(x, numbers.Number) and not isinstance(x, bool) and ok(float(x))


def pct(x, d=1):
    return es(f"{x * 100:,.{d}f}") + "%" if _isnum(x) else ("—" if not isinstance(x, str) else x)


def num(x, d=0):
    return es(f"{x:,.{d}f}") if _isnum(x) else ("—" if not isinstance(x, str) else x)


def mult(x, d=1):
    return es(f"{x:,.{d}f}") + "x" if _isnum(x) else ("—" if not isinstance(x, str) else x)


def money(m, d=1) -> str:
    """Importe en millones de $ → texto corto: 950 M$, 23,8 mil M$, 1,2 billones $."""
    if not _isnum(m):
        return "—"
    a = abs(m)
    if a >= 1e6:
        return num(m / 1e6, d) + " bill. $"
    if a >= 1e3:
        return num(m / 1e3, d) + " mil M$"
    return num(m, 0) + " M$"


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


GROWTH_HINTS = ("crec", "cagr", "variación", "var.", "δ", "sorpresa", "frente a la guía", "rentabilidad anual", "margen de seguridad",
                "plusvalía", "rentab.")
POS, NEG, BOLD_BG = "#1e7b4a", "#b42318", "#eef3fa"


def is_inverse(label) -> bool:
    """Métricas en las que bajar es bueno (p. ej. número de acciones: bajar = recompra)."""
    l = str(label).lower()
    return "acciones" in l or "deuda" in l


def is_growth(label) -> bool:
    l = str(label).lower()
    return any(h in l for h in GROWTH_HINTS)


def _sign_css(v) -> str:
    if not _isnum(v) or v == 0:
        return ""
    return f"color: {POS};" if v > 0 else f"color: {NEG};"


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


INDENT = "\u2003"  # sangría para las partidas de detalle


def _mixed(col) -> bool:
    """Columna con textos y números a la vez: Arrow no la admite como número, así que se muestra como texto."""
    return col.dtype == object and any(isinstance(x, str) for x in col) and any(_isnum(x) for x in col)


def show_rows_table(df: pd.DataFrame, kinds: dict | None = None, height: int | None = None,
                    bold: set | None = None, indent: set | None = None):
    """Tabla con filas = conceptos y columnas = años; cada fila con su formato.

    bold: filas clave (totales) en negrita y con fondo suave · indent: filas de detalle con sangría.
    Los números se alinean a la derecha; negativos en rojo; en las filas de crecimiento, positivos en verde.
    """
    kinds = kinds or {}
    bold, indent = set(bold or ()), set(indent or ())
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    labels = [(INDENT + str(i) if i in indent else str(i)) for i in out.index]
    rk = {lab: (kinds.get(i) or kind_of(i)) for lab, i in zip(labels, df.index)}
    is_bold = {lab: i in bold for lab, i in zip(labels, df.index)}
    growth = {lab: is_growth(i) for lab, i in zip(labels, df.index)}
    out.index = labels
    out = out.loc[~out.index.duplicated()]
    if any(_mixed(out[c]) for c in out.columns):  # algún texto entre los números: todo a texto ya formateado
        out = out.astype(object)
        for lab in out.index:
            out.loc[lab] = [fmt_cell(v, rk[lab]) if not isinstance(v, str) else v for v in out.loc[lab]]

    def _row(r):
        b = is_bold.get(r.name, False)
        css = []
        for v in r:
            c = f"font-weight: 700; background-color: {BOLD_BG};" if b else ""
            if _isnum(v):
                if growth.get(r.name):
                    c += _sign_css(-v) if is_inverse(r.name) else _sign_css(v)
                elif v < 0:
                    c += f" color: {NEG};"
            elif isinstance(v, str) and v[:1] in ("-", "−") and len(v) > 1 and v[1:2].isdigit():
                c += f" color: {NEG};"
            css.append(c)
        return css

    sty = out.style.apply(_row, axis=1)
    for lab in out.index:
        sty = sty.format(lambda v, k=rk[lab]: fmt_cell(v, k), subset=pd.IndexSlice[[lab], :], na_rep="—")
    try:
        sty = sty.map_index(lambda v: f"font-weight: 700; background-color: {BOLD_BG};" if is_bold.get(v) else "", axis=0)
    except AttributeError:
        pass
    ccfg = {c: st.column_config.Column(c, alignment="right") for c in out.columns}
    st.dataframe(sty, width="stretch", height=height or min(38 + 35 * len(out), 900), column_config=ccfg)


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
    """Tabla con columnas = conceptos (formato por columna).

    Los valores siguen siendo números (al pulsar el título de una columna se ordena bien) y solo cambia cómo se muestran.
    Crecimientos y variaciones en verde (positivo) o rojo (negativo).
    """
    kinds = kinds or {}
    column_config = column_config or {}
    out = df.copy()
    out = out.loc[:, ~out.columns.duplicated()]
    for c in out.columns:
        if c not in column_config and out[c].dtype == object and all((x is None) or _isnum(x) or x != x for x in out[c]):
            out[c] = pd.to_numeric(out[c], errors="coerce")  # números con huecos (None) → numérica, para que no salga «None»
        if c not in column_config and _mixed(out[c]):
            k = kinds.get(c) or kind_of(c)
            out[c] = [fmt_cell(v, k) for v in out[c]]
    sty = out.style
    for c in out.columns:
        if c in column_config:
            continue
        k = kinds.get(c) or kind_of(c)
        sty = sty.format(lambda v, k=k: fmt_cell(v, k), subset=[c], na_rep="—")
        if is_growth(c) and k == "pct":
            sty = sty.map((lambda v: _sign_css(-v) if _isnum(v) else "") if is_inverse(c) else _sign_css, subset=[c])
    st.dataframe(sty, width="stretch", height=height or min(38 + 35 * len(out), 700), column_config=column_config or None)


def kv_table(d: dict):
    rows = [fmt_cell(v, kind_of(k)) for k, v in d.items()]
    df = pd.DataFrame({"Valor": rows}, index=[str(k) for k in d.keys()])
    st.dataframe(df, width="stretch", height=38 + 35 * len(df),
                 column_config={"Valor": st.column_config.TextColumn("Valor", alignment="right")})


def _register_template():
    """Plantilla común de los gráficos: fondo blanco, rejilla suave, números en español y colores fijos por orden."""
    import plotly.io as pio
    t = go.layout.Template(pio.templates["plotly_white"])
    t.layout.separators = ",."
    t.layout.colorway = [BLUE, AMBER, GREEN, "#7c5cbf", "#3a9fb5", MUTED]
    t.layout.font = dict(family="Source Sans 3, Arial", size=12, color=TEXT)
    t.layout.paper_bgcolor = t.layout.plot_bgcolor = "#ffffff"
    t.layout.xaxis.gridcolor = "#eef0f3"
    t.layout.yaxis.gridcolor = "#e3e6eb"
    t.layout.xaxis.linecolor = t.layout.yaxis.zerolinecolor = "#c9ced6"
    t.layout.hoverlabel = dict(bgcolor="#ffffff", font_family="Source Sans 3, Arial", bordercolor="#c9ced6")
    t.layout.legend = dict(orientation="h", yanchor="top", y=-0.12, x=0, font=dict(size=11))
    t.layout.bargap = 0.25
    t.layout.bargroupgap = 0.08
    pio.templates["terminal"] = t
    pio.templates.default = "terminal"


_register_template()


def fig_layout(fig: go.Figure, title: str = "", h: int = 300, unit: str = ""):
    """unit: texto corto de la unidad del eje Y (p. ej. «M$»); se muestra junto al título."""
    if unit:
        title = f"{title} <span style='font-size:12px;color:{MUTED}'>· {unit}</span>"
    fig.update_layout(template="terminal", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", height=h,
                      margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      title=dict(text=title, font=dict(size=15, family="Source Sans 3, Arial", color=TEXT)),
                      font=dict(family="Source Sans 3, Arial", size=12, color=TEXT), legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, font=dict(size=11)),
                      xaxis=dict(gridcolor="#eef0f3", type="category", linecolor="#c9ced6"), yaxis=dict(gridcolor="#e3e6eb", zerolinecolor="#c9ced6"),
                      hoverlabel=dict(bgcolor="#ffffff", font_family="Source Sans 3, Arial"), hovermode="x unified")
    return fig
