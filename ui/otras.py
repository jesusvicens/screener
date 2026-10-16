from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from terminal import pipeline, screener, storage
from ui.common import show_cols_table

@st.cache_data(ttl=3600, show_spinner=False)
def _screen_table(base_stamp: float, mk_stamp: float):
    base = screener.load_base(9999)
    mk, _age = screener.load_market()
    return screener.with_valuation(base, mk)


def _go_company(t: str):
    st.session_state["ticker"] = t
    st.switch_page(st.session_state["_page_empresa"])


def _to_ui(m, v):
    return None if v is None else (v * 100 if screener.METRIC_KIND[m] == "pct" else v)


def _from_ui(m, v):
    return None if v is None else (v / 100 if screener.METRIC_KIND[m] == "pct" else v)


def _apply_preset(filters: dict):
    st.session_state["scr_metrics"] = list(filters)
    for m, (lo, hi) in filters.items():
        st.session_state[f"scr_lo_{m}"] = _to_ui(m, lo)
        st.session_state[f"scr_hi_{m}"] = _to_ui(m, hi)


def _user_presets() -> dict:
    try:
        return (storage.load("_FILTROS") or {}).get("filtros", {})
    except Exception:  # noqa: BLE001
        return {}


def _on_preset():
    name = st.session_state.get("scr_preset")
    allp = {**screener.PRESETS, **_user_presets()}
    if name in allp:
        _apply_preset({m: tuple(v) for m, v in allp[name].items()})


# ------------------------------------------------------------------ Screener
def screener_page():
    st.markdown("<span class='subtle'>SCREENER · TODAS LAS COTIZADAS DE EE. UU.</span>", unsafe_allow_html=True)
    st.markdown("# Screener")
    base = screener.load_base(7)
    mk, mk_age = screener.load_market()
    c = st.columns([3, 1, 1])
    upd_base = c[1].button("↻ Fundamentales (≈1-2 min)", width="stretch", help="Descarga de la SEC. Se refresca sola cada semana.")
    upd_mk = c[2].button("↻ Precios y sectores", width="stretch", help="Una sola llamada al screener público de Nasdaq.")
    if base is None or upd_base:
        bar = st.progress(0.0, "Descargando de la SEC…")
        base = screener.build_base(progress=lambda p, m: bar.progress(p, m))
        screener.save_base(base)
        bar.empty()
    if mk is None or (mk_age or 0) > 24 or upd_mk:
        with st.spinner("Descargando precios y sectores…"):
            mk = screener.refresh_market()
        mk_age = 0.0
    base_stamp = screener.BASE_FILE.stat().st_mtime
    mk_stamp = screener.PRICES_FILE.stat().st_mtime if screener.PRICES_FILE.exists() else 0.0
    df = _screen_table(base_stamp, mk_stamp)
    Y = int(df["Año datos"].iloc[0])
    c[0].caption(f"{len(df):,} empresas · fundamentales del ejercicio {Y} (SEC, hace {(time.time() - base_stamp) / 86400:.1f} días) · "
                 f"precios hace {mk_age or 0:.0f} h · {df['Precio'].notna().sum():,} con cotización")

    st.session_state.setdefault("scr_metrics", list(screener.PRESETS["Fisher / Munger: calidad que crece"]))
    if "scr_init" not in st.session_state:
        _apply_preset(screener.PRESETS["Fisher / Munger: calidad que crece"])
        st.session_state["scr_init"] = True

    with st.container(border=True):
        st.markdown("## Filtros")
        r = st.columns([1.4, 1, 1, 1.2, 1.4])
        presets = list(screener.PRESETS) + list(_user_presets())
        r[0].selectbox("Plantilla", presets, index=None, placeholder="Cargar una plantilla…", key="scr_preset", on_change=_on_preset)
        text = r[1].text_input("Buscar", placeholder="Ticker o nombre")
        exch = r[2].multiselect("Mercado", sorted(df["Mercado"].dropna().unique()), default=["Nasdaq", "NYSE"], placeholder="Todos")
        sectors = r[3].multiselect("Sector", sorted(s for s in df["Sector"].dropna().unique() if s != "—"), placeholder="Todos")
        ind_opts = sorted(i for i in df[df["Sector"].isin(sectors)]["Industria"].dropna().unique() if i != "—") if sectors else \
            sorted(i for i in df["Industria"].dropna().unique() if i != "—")
        industries = r[4].multiselect("Industria", ind_opts, placeholder="Todas")

        labels = {m: f"{g} · {m}" for m, g, _k, _d in screener.METRICS}
        st.multiselect("Métricas por las que filtrar (añade o quita)", [m for m, *_ in screener.METRICS], key="scr_metrics",
                       format_func=lambda m: labels[m])
        filters = {}
        mets = st.session_state["scr_metrics"]
        for i in range(0, len(mets), 3):
            cols = st.columns(3)
            for j, m in enumerate(mets[i:i + 3]):
                with cols[j]:
                    unit = " (%)" if screener.METRIC_KIND[m] == "pct" else ""
                    st.markdown(f"<div class='subtle' style='margin-bottom:.1rem'>{m}{unit}</div>", unsafe_allow_html=True)
                    a1, a2 = st.columns(2)
                    st.session_state.setdefault(f"scr_lo_{m}", None)
                    st.session_state.setdefault(f"scr_hi_{m}", None)
                    lo = a1.number_input("mín", key=f"scr_lo_{m}", placeholder="mín", label_visibility="collapsed", help=screener.METRIC_HELP[m])
                    hi = a2.number_input("máx", key=f"scr_hi_{m}", placeholder="máx", label_visibility="collapsed")
                    filters[m] = (_from_ui(m, lo), _from_ui(m, hi))
        sv = st.columns([2, 1, 3])
        name = sv[0].text_input("Guardar estos filtros como…", placeholder="Nombre de la plantilla", label_visibility="collapsed")
        if sv[1].button("Guardar plantilla", width="stretch") and name:
            up = _user_presets()
            up[name] = {m: list(v) for m, v in filters.items()}
            try:
                storage.save("_FILTROS", {"filtros": up})
                st.toast(f"Plantilla «{name}» guardada")
            except Exception as e:  # noqa: BLE001
                st.error(f"No se ha podido guardar: {e}")

    res = screener.apply_filters(df, filters, exch, text, sectors, industries)
    st.markdown(f"## Resultado · {len(res):,} empresas")
    core = ["Empresa", "Sector", "Precio", "Capitalización (M$)", "PER"]
    default_cols = core + [m for m in mets if m not in core]
    for extra in ("CAGR ventas 5a", "CAGR BPA 5a", "ROE", "Margen operativo"):
        if extra not in default_cols and len(default_cols) < 12:
            default_cols.append(extra)
    allcols = ["Empresa", "Mercado", "Sector", "Industria", "País", "BPA"] + [m for m, *_ in screener.METRICS]
    oc = st.columns([3, 1.3, 0.8])
    cols = oc[0].multiselect("Columnas", allcols, default=default_cols, key="scr_cols")
    sort_opts = [c for c in cols if c not in ("Empresa", "Mercado", "Sector", "Industria", "País")] or ["Ventas (M$)"]
    sort_by = oc[1].selectbox("Ordenar por", sort_opts, index=sort_opts.index("CAGR BPA 5a") if "CAGR BPA 5a" in sort_opts else 0)
    asc = oc[2].toggle("Ascendente", False)
    out = res.sort_values(sort_by, ascending=asc, na_position="last")[["Ticker"] + cols].head(1000).set_index("Ticker")
    kinds = {m: k for m, k in screener.METRIC_KIND.items()}
    kinds.update({"BPA": "ps", "Precio": "ps", "Años caída ventas": "int", "Años caída BPA": "int", "Años con pérdidas": "int"})
    show_cols_table(out, height=600, kinds={k: v for k, v in kinds.items() if k in out.columns})
    if len(res) > 1000:
        st.caption("Muestro las 1.000 primeras; afina los filtros o descarga el CSV completo.")
    b = st.columns([2, 1, 1])
    pick = b[0].selectbox("Abrir ficha", list(out.index), index=None, placeholder="Elige una empresa del resultado…")
    if pick:
        _go_company(pick)
    b[1].download_button("⬇ CSV", res.drop(columns=[c for c in res.columns if c.startswith("_")]).to_csv(index=False).encode("utf-8"),
                         "screener.csv", width="stretch")
    if b[2].button("→ Analizar en lote (máx. 60)", width="stretch"):
        st.session_state["lote_tickers"] = ", ".join(list(out.index)[:60])
        st.switch_page(st.session_state["_page_lote"])
    st.caption("Datos: frames de la SEC (el ejercicio que mejor encaja con el año natural; saldos al cierre más cercano a diciembre), "
               "BPA y acciones ajustados por splits. Precios, capitalización y sector: screener público de Nasdaq. "
               "Ojo con empresas que reportan en otra divisa (PER y P/V sin sentido) y con bancos/aseguradoras (sin margen bruto).")


# ------------------------------------------------------------------ Lote
def lote_page():
    st.markdown("<span class='subtle'>ANÁLISIS EN LOTE</span>", unsafe_allow_html=True)
    st.markdown("# Análisis completo en lote")
    st.caption("Pasa tu modelo completo (examen financiero automático, proyección en 4 escenarios, test de cobertura y margen de seguridad) "
               "por una lista de empresas. Usa tus supuestos guardados si los hay; si no, las propuestas por fase. Cada empresa tarda ~1-2 s.")
    default = st.session_state.get("lote_tickers", "ADBE, MSFT, CPRT, V, MA")
    txt = st.text_area("Tickers (separados por comas o espacios)", default, height=100)
    c = st.columns(3)
    use_saved = c[0].checkbox("Usar mis análisis guardados", True)
    only_compensa = c[1].checkbox("Mostrar solo «Compensa»", False)
    run = c[2].button("Analizar", type="primary", width="stretch")
    if run:
        tickers = [t.strip().upper() for t in txt.replace(",", " ").split() if t.strip()]
        rows, errs = [], []
        bar = st.progress(0.0)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers), f"{t} ({i + 1}/{len(tickers)})")
            try:
                meta, fin, hist = pipeline.load_company(t)
                saved = storage.load(t) if use_saved else {}
                ca = pipeline.analyze(meta, fin, hist, saved=saved)
                rows.append(pipeline.summary_row(ca))
            except Exception as e:  # noqa: BLE001
                errs.append(f"{t}: {e}")
        bar.empty()
        st.session_state["lote_result"] = pd.DataFrame(rows)
        st.session_state["lote_errs"] = errs
    df = st.session_state.get("lote_result")
    if df is not None and not df.empty:
        if only_compensa and "Veredicto" in df:
            df = df[df["Veredicto"] == "Compensa"]
        sort_col = "Margen de seguridad" if "Margen de seguridad" in df else "Nota financiera"
        df = df.sort_values(sort_col, ascending=False)
        show_cols_table(df.set_index("Ticker"), height=min(80 + 35 * len(df), 700))
        st.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8"), "lote.csv")
        pick = st.selectbox("Abrir ficha", list(df["Ticker"]), index=None, placeholder="Elige una empresa…")
        if pick:
            _go_company(pick)
    for e in st.session_state.get("lote_errs", []):
        st.caption(f"⚠ {e}")


# ------------------------------------------------------------------ Mis análisis
def mis_analisis_page():
    st.markdown("<span class='subtle'>MIS ANÁLISIS</span>", unsafe_allow_html=True)
    st.markdown("# Mis análisis guardados")
    st.caption(f"Almacenamiento: {storage.backend()}.")
    try:
        items = storage.list_all()
    except Exception as e:  # noqa: BLE001
        st.error(f"No he podido leer los análisis: {e}")
        return
    if not items:
        st.info("Aún no has guardado ninguno. Abre una empresa y pulsa «Guardar análisis».")
        return
    items = [it for it in items if not str(it.get("ticker", "")).startswith("_")]
    if not items:
        st.info("Aún no has guardado ninguno. Abre una empresa y pulsa «Guardar análisis».")
        return
    rows = []
    for it in items:
        r = dict(it.get("resumen") or {})
        r.setdefault("Ticker", it.get("ticker"))
        r["Actualizado"] = it.get("actualizado")
        r["Tesis"] = (it.get("notas") or "")[:80]
        rows.append(r)
    df = pd.DataFrame(rows)
    show_cols_table(df.set_index("Ticker"), height=min(80 + 35 * len(df), 700))
    st.caption("El resumen es la foto del momento en que guardaste (precio y valoración de ese día).")
    pick = st.selectbox("Abrir ficha", list(df["Ticker"]), index=None, placeholder="Elige una empresa…")
    if pick:
        _go_company(pick)
