from __future__ import annotations

import io
import time
from datetime import date

import pandas as pd
import streamlit as st

from terminal import pipeline, screener, storage
from ui.ayuda import explica
from ui.common import alto_filas, company_url, num, pct, show_cols_table

@st.cache_data(ttl=3600, show_spinner=False)
def _screen_table(base_stamp: float, mk_stamp: float, notas_stamp: float = 0.0):
    base = screener.load_base(9999)
    mk, _age = screener.load_market()
    return screener.with_notas(screener.with_valuation(base, mk))


def _go_company(t: str):
    st.switch_page(st.session_state["_page_empresa"], query_params={"ticker": t})


def _to_ui(m, v):
    return None if v is None else (v * 100 if screener.METRIC_KIND[m] == "pct" else v)


def _from_ui(m, v):
    return None if v is None else (v / 100 if screener.METRIC_KIND[m] == "pct" else v)


def _apply_preset(filters: dict):
    sp = st.session_state.setdefault("_scr_persist", {})
    st.session_state["scr_metrics"] = sp["scr_metrics"] = list(filters)
    for m, v in filters.items():
        lo, hi = v[0], v[1]
        st.session_state[f"scr_lo_{m}"] = sp[f"scr_lo_{m}"] = _to_ui(m, lo)
        st.session_state[f"scr_hi_{m}"] = sp[f"scr_hi_{m}"] = _to_ui(m, hi)
        if m in screener.AVG_GROWTH:
            n = int(v[2]) if len(v) > 2 and v[2] else screener.AVG_DEFAULT
            st.session_state[f"scr_n_{m}"] = sp[f"scr_n_{m}"] = n


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
    # La tabla de resultados ocupa casi todo el ancho de la pantalla.
    st.markdown("<style>.block-container{max-width:98% !important;padding-left:1.5rem;padding-right:1.5rem;}</style>",
                unsafe_allow_html=True)
    st.markdown("<span class='subtle'>SCREENER · COTIZADAS DE EE. UU. Y EUROPA</span>", unsafe_allow_html=True)
    st.markdown("# Screener")
    _screener_body()


def listas_page():
    # tablas a todo el ancho de la pantalla, como en el Screener
    st.markdown("<style>.block-container{max-width:98% !important;padding-left:1.5rem;padding-right:1.5rem;}</style>",
                unsafe_allow_html=True)
    st.markdown("<span class='subtle'>LISTAS</span>", unsafe_allow_html=True)
    st.markdown("# Mis listas")
    from ui import prioridad
    prioridad.body()


def _screener_body():
    explica("screener")
    base = screener.load_base(7)
    mk, mk_age = screener.load_market()
    eu_old = not screener.EU_MARKET_FILE.exists() or (time.time() - screener.EU_MARKET_FILE.stat().st_mtime) > 24 * 3600
    if base is None or mk is None or (mk_age or 0) > 24 or eu_old:
        with st.spinner("Cargando los datos preparados esta noche…"):
            if any(screener.sync_from_repo().values()):
                base = screener.load_base(7)
                mk, mk_age = screener.load_market()
    c = st.columns([3, 1, 1])
    upd_base = c[1].button("↻ Fundamentales (≈1-2 min)", width="stretch", help="Descarga de la SEC. Se refresca sola cada semana.")
    upd_mk = c[2].button("↻ Precios y sectores", width="stretch", help="Una sola llamada al screener público de Nasdaq.")
    if base is None or upd_base:  # (también si la caché es de una versión sin series anuales)
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
    eu_stamp = sum(f.stat().st_mtime for f in (screener.EU_BASE_FILE, screener.EU_MARKET_FILE) if f.exists())
    df = _screen_table(base_stamp + eu_stamp, mk_stamp, screener.NOTAS_FILE.stat().st_mtime if screener.NOTAS_FILE.exists() else 0.0)
    Y = int(pd.to_numeric(df.loc[pd.to_numeric(df["CIK"], errors="coerce") > 0, "Año datos"], errors="coerce").max())
    n_eu = int((pd.to_numeric(df["CIK"], errors="coerce").fillna(0) == 0).sum())
    na_age = screener.notas_age_days()
    c[0].caption(("" if na_age is None else f"Notas del examen financiero: hace {na_age:.0f} días · ") + f"{num(len(df))} empresas ({num(n_eu)} europeas) · fundamentales del ejercicio {Y} (SEC, hace {(time.time() - base_stamp) / 86400:.1f} días; europeas: ESEF) · "
                 f"precios hace {mk_age or 0:.0f} h · {num(df['Precio'].notna().sum())} con cotización")

    # Streamlit borra el estado de los controles al cambiar de página: lo restauramos desde una copia.
    sp = st.session_state.setdefault("_scr_persist", {})
    if not sp:
        default = screener.PRESETS["Fisher / Munger: calidad que crece"]
        sp["scr_metrics"] = list(default)
        for m, (lo, hi) in default.items():
            sp[f"scr_lo_{m}"], sp[f"scr_hi_{m}"] = _to_ui(m, lo), _to_ui(m, hi)
    for k, v in sp.items():
        if k not in st.session_state:
            st.session_state[k] = v

    with st.container(border=True):
        st.markdown("## Filtros")
        r = st.columns([1.4, 1, 1, 1.2, 1.4])
        presets = list(screener.PRESETS) + list(_user_presets())
        r[0].selectbox("Plantilla", presets, index=None, placeholder="Cargar una plantilla…", key="scr_preset", on_change=_on_preset)
        text = r[1].text_input("Buscar", placeholder="Ticker o nombre")
        eu_ex = sorted(df.loc[pd.to_numeric(df["CIK"], errors="coerce").fillna(0) == 0, "Mercado"].dropna().unique())
        exch = r[2].multiselect("Mercado", sorted(df["Mercado"].dropna().unique()), default=["Nasdaq", "NYSE"] + eu_ex, placeholder="Todos",
                                help="Por defecto, Nasdaq, NYSE y las bolsas europeas")
        sectors = r[3].multiselect("Sector", sorted(s for s in df["Sector"].dropna().unique() if s != "—"), placeholder="Todos")
        ind_opts = sorted(i for i in df[df["Sector"].isin(sectors)]["Industria"].dropna().unique() if i != "—") if sectors else \
            sorted(i for i in df["Industria"].dropna().unique() if i != "—")
        industries = r[4].multiselect("Industria", ind_opts, placeholder="Todas")

        labels = {m: f"{g} · {m}" for m, g, _k, _d in screener.METRICS}
        st.multiselect("Métricas por las que filtrar (añade o quita)", [m for m, *_ in screener.METRICS], key="scr_metrics",
                       format_func=lambda m: labels[m])
        filters = {}
        navg: dict[str, int] = {}
        mets = st.session_state["scr_metrics"]
        for i in range(0, len(mets), 3):
            cols = st.columns(3)
            for j, m in enumerate(mets[i:i + 3]):
                with cols[j]:
                    unit = " (%)" if screener.METRIC_KIND[m] == "pct" else ""
                    st.markdown(f"<div class='subtle' style='margin-bottom:.1rem'>{m}{unit}</div>", unsafe_allow_html=True)
                    is_avg = m in screener.AVG_GROWTH
                    a1, a2, *a3 = st.columns([1, 1, 0.9]) if is_avg else st.columns(2)
                    st.session_state.setdefault(f"scr_lo_{m}", None)
                    st.session_state.setdefault(f"scr_hi_{m}", None)
                    lo = a1.number_input("mín", key=f"scr_lo_{m}", placeholder="mín", label_visibility="collapsed", help=screener.METRIC_HELP[m])
                    hi = a2.number_input("máx", key=f"scr_hi_{m}", placeholder="máx", label_visibility="collapsed")
                    if is_avg:
                        st.session_state.setdefault(f"scr_n_{m}", screener.AVG_DEFAULT)
                        navg[m] = a3[0].selectbox("años", screener.AVG_YEARS, key=f"scr_n_{m}", format_func=lambda n: f"{n} años",
                                                  label_visibility="collapsed", help="Número de años de la media")
                    filters[m] = (_from_ui(m, lo), _from_ui(m, hi))
        sv = st.columns([2, 1, 3])
        name = sv[0].text_input("Guardar estos filtros como…", placeholder="Nombre de la plantilla", label_visibility="collapsed")
        if sv[1].button("Guardar plantilla", width="stretch") and name:
            up = _user_presets()
            up[name] = {m: list(v) + ([navg[m]] if m in navg else []) for m, v in filters.items()}
            try:
                storage.save("_FILTROS", {"filtros": up})
                st.toast(f"Plantilla «{name}» guardada")
            except Exception as e:  # noqa: BLE001
                st.error(f"No se ha podido guardar: {e}")

    sp["scr_metrics"] = list(st.session_state["scr_metrics"])
    for m in mets:
        sp[f"scr_lo_{m}"], sp[f"scr_hi_{m}"] = st.session_state.get(f"scr_lo_{m}"), st.session_state.get(f"scr_hi_{m}")
        if m in navg:
            sp[f"scr_n_{m}"] = navg[m]
    df = screener.with_avg_growth(df, navg)
    res = screener.apply_filters(df, filters, exch, text, sectors, industries)
    st.markdown(f"## Resultado · {num(len(res))} empresas")
    core = ["Empresa", "Negocio", "Sector", "Precio", "Capitalización (M$)", "PER", "Nota financiera"]
    default_cols = core + [m for m in mets if m not in core]
    for extra in ("CAGR ventas 5a", "CAGR BPA 5a", "ROE", "Margen operativo"):
        if extra not in default_cols and len(default_cols) < 12:
            default_cols.append(extra)
    allcols = ["Empresa", "Negocio", "Mercado", "Sector", "Industria", "País", "BPA", "Valor estimado"] + [m for m, *_ in screener.METRICS]
    for m in ("Cobertura", "Margen de seguridad"):
        if m in mets and "Valor estimado" not in default_cols:
            default_cols.append("Valor estimado")
    cols = _selector_columnas(allcols, default_cols, mets, sp)
    oc = st.columns([3, 1.3, 0.8, 1.2])
    sort_opts = [c for c in cols if c not in ("Empresa", "Negocio", "Mercado", "Sector", "Industria", "País")] or ["Ventas (M$)"]
    sort_by = oc[1].selectbox("Ordenar por", sort_opts, index=sort_opts.index("CAGR BPA 5a") if "CAGR BPA 5a" in sort_opts else 0)
    asc = oc[2].toggle("Ascendente", False)
    with oc[3]:
        rh = alto_filas("scr_alto") if "Negocio" in cols else None
    res = res.copy()
    if "Negocio" in cols:
        from terminal import descripciones
        from ui.prioridad import _guardados
        gu = _guardados()
        top = res.sort_values(sort_by, ascending=asc, na_position="last").head(1000)
        res["Negocio"] = None
        res.loc[top.index, "Negocio"] = [descripciones.para(t, gu) for t in top["Ticker"]]
    out = res.sort_values(sort_by, ascending=asc, na_position="last")[["Ticker"] + cols].head(1000).set_index("Ticker")
    ren = {m: f"{m} {navg.get(m, screener.AVG_DEFAULT)}a" for m in screener.AVG_GROWTH if m in out.columns}
    out = out.rename(columns=ren)
    kinds = {m: k for m, k in screener.METRIC_KIND.items()}
    kinds.update({v: "pct" for v in ren.values()})
    kinds.update({"BPA": "ps", "Precio": "ps", "Valor estimado": "ps", "Años caída ventas": "int", "Años caída BPA": "int", "Años con pérdidas": "int",
                  "Preguntas no aplicables": "int"})
    ccfg = {}
    if "Negocio" in out.columns:
        out["Negocio"] = out["Negocio"].fillna("")
        ccfg["Negocio"] = st.column_config.TextColumn("Negocio", width="large", help="Qué hace la empresa: tu «En una frase» si tienes dossier; si no, el resumen de su actividad (Yahoo Finance/Nasdaq, en inglés). Pasa el ratón para leerlo entero.")
    if "Empresa" in out.columns:
        out["Empresa"] = [company_url(t, n) for t, n in zip(out.index, out["Empresa"])]
        ccfg["Empresa"] = st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$",
                                                     help="Clic para abrir la ficha en una pestaña nueva")
    show_cols_table(out, height=700, kinds={k: v for k, v in kinds.items() if k in out.columns}, column_config=ccfg, row_height=rh)
    if any(c in out.columns for c in ("Cobertura", "Margen de seguridad", "Valor estimado")):
        st.caption("Cobertura, margen de seguridad y valor estimado salen de la **proyección estándar** (los 4 escenarios que la ficha "
                   "propone por fase, r = 10 %, n = 10 años), recalculados con el precio de hoy. Si tienes la empresa analizada con "
                   "tus supuestos, la ficha manda. Cobertura ∞: ningún escenario queda por debajo del umbral. "
                   f"Se dejan en blanco {num(int(df.get('Valoración dudosa', pd.Series(dtype=bool)).fillna(False).sum()))} empresas cuyo valor "
                   "estimado sale de más de 5 veces el precio o que presentan en otra divisa sin tipo de cambio: casi siempre son datos "
                   "que no cuadran (un split reciente, un ADR) y conviene mirarlas en la ficha.")
    if len(res) > 1000:
        st.caption("Muestro las 1.000 primeras; afina los filtros o descarga el CSV completo.")
    lb = st.columns([3, 1.4, 1])
    lpick = lb[0].multiselect("Añadir a una lista", list(out.index), placeholder="Añadir empresas del resultado a una de tus listas…",
                              label_visibility="collapsed")
    from ui.prioridad import _guardar, _listas
    from terminal import listas as L
    lg = lb[1].selectbox("Lista", _listas()["grupos"], key="scr_lista", label_visibility="collapsed")
    if lb[2].button("Añadir a la lista", width="stretch", disabled=not lpick):
        _guardar(L.add(_listas(), lpick, lg), f"{len(lpick)} añadidas a «{lg}»")
    b = st.columns([2, 1, 1])
    pick = b[0].selectbox("Abrir ficha", list(out.index), index=None, placeholder="Elige una empresa del resultado…")
    if pick:
        _go_company(pick)
    b[1].download_button("⬇ CSV", res.drop(columns=[c for c in res.columns if c.startswith("_")]).to_csv(index=False).encode("utf-8"),
                         "screener.csv", width="stretch")
    st.caption("Datos: frames de la SEC (el ejercicio que mejor encaja con el año natural; saldos al cierre más cercano a diciembre), "
               "BPA y acciones ajustados por splits. Precios, capitalización y sector: screener público de Nasdaq. "
               "Ojo con empresas que reportan en otra divisa (PER y P/V sin sentido) y con bancos/aseguradoras (sin margen bruto).")


# ------------------------------------------------------------------ columnas del screener
def _grupos_columnas() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {"Empresa": ["Empresa", "Negocio", "Mercado", "Sector", "Industria", "País"]}
    for m, gr, _k, _d in screener.METRICS:
        g.setdefault(gr, []).append(m)
    g["Valoración"] = g.get("Valoración", []) + ["BPA", "Valor estimado"]
    orden = ["Empresa", "Valoración", "Examen", "Tamaño", "Crecimiento", "Márgenes", "Rentabilidad", "Capital", "Salud", "Consistencia"]
    return {k: g[k] for k in orden if k in g} | {k: v for k, v in g.items() if k not in orden}


def _cols_por_defecto(grupos, default_cols):
    for gr, opts in grupos.items():
        st.session_state[f"scr_cg_{gr}"] = [c for c in opts if c in default_cols]


def _selector_columnas(allcols, default_cols, mets, sp) -> list[str]:
    """Columnas visibles: casillas agrupadas por tema (se ven todas a la vez y se quitan con un clic)."""
    grupos = _grupos_columnas()
    for gr, opts in grupos.items():
        k = f"scr_cg_{gr}"
        if k not in st.session_state:
            st.session_state[k] = sp.get(k, [c for c in opts if c in default_cols])
    sel = [c for gr in grupos for c in (st.session_state.get(f"scr_cg_{gr}") or [])]
    extra = [m for m in mets if m not in sel]
    todas = sel + extra
    st.markdown(f"<div class='subtle' style='margin:.2rem 0 .1rem'><b>Columnas visibles ({len(todas)}):</b> "
                + html_escape(", ".join(todas)).replace("$", "&#36;") + "</div>", unsafe_allow_html=True)
    with st.expander("🧱 Elegir columnas", expanded=False):
        st.caption("Pulsa una columna para mostrarla u ocultarla. Las métricas por las que filtras se ven siempre.")
        for gr, opts in grupos.items():
            c = st.columns([1, 7], vertical_alignment="center")
            c[0].markdown(f"<div class='subtle' style='font-weight:700'>{gr}</div>", unsafe_allow_html=True)
            c[1].pills(gr, opts, selection_mode="multi", key=f"scr_cg_{gr}", label_visibility="collapsed", wrap=True)
        b = st.columns([1, 1, 4])
        b[0].button("Por defecto", on_click=_cols_por_defecto, args=(grupos, default_cols), width="stretch")
        b[1].button("Solo lo básico", on_click=_cols_por_defecto,
                    args=(grupos, ["Empresa", "Negocio", "Precio", "PER", "Nota financiera"]), width="stretch")
    for gr in grupos:
        sp[f"scr_cg_{gr}"] = list(st.session_state.get(f"scr_cg_{gr}") or [])
    sel = [c for gr in grupos for c in (st.session_state.get(f"scr_cg_{gr}") or [])]
    return sel + [m for m in mets if m not in sel]


# ------------------------------------------------------------------ Lote
def lote_page():
    st.markdown("<span class='subtle'>ANÁLISIS EN LOTE</span>", unsafe_allow_html=True)
    st.markdown("# Análisis completo en lote")
    explica("lote")
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
    from ui import conclusion as CO
    from ui.common import company_url as _cu
    st.markdown("<span class='subtle'>MIS ANÁLISIS</span>", unsafe_allow_html=True)
    st.markdown("# Mis análisis")
    try:
        items = storage.list_all()
    except Exception as e:  # noqa: BLE001
        st.error(f"No he podido leer los análisis: {e}")
        return
    items = [it for it in (items or []) if it.get("ticker") and not str(it.get("ticker")).startswith("_")]
    if not items:
        st.info("Aún no has guardado ninguno. Abre una empresa y pulsa «Guardar análisis».")
        return
    try:
        from terminal import listas as L
        dl = L.load()
    except Exception:  # noqa: BLE001
        dl = {"empresas": {}}
    try:
        from ui import universo
        uni = universo.table()
        idx = uni.drop_duplicates("Ticker").set_index("Ticker") if uni is not None else None
    except Exception:  # noqa: BLE001
        idx = None
    ops = ["Todas"] + list(CO.OPINIONES) + ["Sin conclusión"]
    c = st.columns([3, 1.3])
    filtro = c[0].segmented_control("Opinión", ops, default="Todas", key="mis_op", label_visibility="collapsed") or "Todas"
    orden = c[1].selectbox("Orden", ["Opinión", "Nombre", "Más reciente", "Margen de seguridad"], key="mis_orden",
                           label_visibility="collapsed", format_func=lambda o: f"Ordenar por: {o.lower()}")
    st.caption("Tu conclusión de cada empresa que has analizado. Se edita aquí («✏️») o en su ficha → Seguimiento → Mis notas y bitácora. "
               "Las cifras son las del día que guardaste el análisis.")
    rows = []
    for it in items:
        t = it.get("ticker")
        con = it.get("conclusion") or {}
        res = it.get("resumen") or {}
        rows.append((t, it, con, res))
    if filtro == "Sin conclusión":
        rows = [r for r in rows if not r[2].get("opinion")]
    elif filtro != "Todas":
        rows = [r for r in rows if r[2].get("opinion") == filtro]
    rank = {o: i for i, o in enumerate(CO.OPINIONES)}
    key = {"Opinión": lambda r: (rank.get(r[2].get("opinion"), 99), str(r[0])),
           "Nombre": lambda r: str((r[3].get("Empresa") or r[0])).lower(),
           "Más reciente": lambda r: str(r[1].get("actualizado") or ""),
           "Margen de seguridad": lambda r: -(r[3].get("Margen de seguridad") or -9)}[orden]
    rows.sort(key=key, reverse=(orden == "Más reciente"))
    if not rows:
        st.caption("Ninguna empresa con esa opinión.")
    for t, it, con, res in rows:
        nombre = res.get("Empresa") or (str(idx.loc[t, "Empresa"]) if idx is not None and t in idx.index else t)
        with st.container(border=True):
            a = st.columns([3.6, 1, 1, 1, 0.6], vertical_alignment="top")
            ls = ", ".join((dl["empresas"].get(t) or {}).get("listas", []))
            url = _cu(t, nombre).split("#")[0]
            a[0].markdown(f"<a href='{url}' target='_blank' style='font-weight:700;font-size:1.05rem;color:#1f2937;text-decoration:none'>"
                          f"{html_escape(str(nombre))}</a> <span style='color:#6b7280;font-size:.8rem'>{t}"
                          + (f" · {html_escape(ls)}" if ls else "") + "</span>", unsafe_allow_html=True)
            blq = CO.html_bloque(con)
            a[0].markdown(f"<div style='font-size:.9rem;line-height:1.4;margin-top:.2rem'>{blq}</div>" if blq else
                          "<div style='color:#9ca3af;font-size:.85rem'>Sin conclusión todavía.</div>", unsafe_allow_html=True)
            nota = res.get("Nota final") or res.get("Nota financiera")
            a[1].metric("Nota", "—" if nota is None else num(nota, 2))
            ms = res.get("Margen de seguridad")
            a[2].metric("Margen seg.", "—" if ms is None else pct(ms))
            a[3].metric("Guardado", str(it.get("actualizado") or "—")[:10])
            with a[4].popover("✏️", help="Editar la conclusión"):
                CO.editor(t, con, key=f"mis_ed_{t}")


def html_escape(x: str) -> str:
    import html as _h
    return _h.escape(x)


# ------------------------------------------------------------------ Cartera
def _load_cartera() -> list[dict]:
    if "cartera_rows" not in st.session_state:
        try:
            st.session_state["cartera_rows"] = (storage.load("_CARTERA") or {}).get("movimientos", [])
        except Exception as e:  # noqa: BLE001
            st.error(f"No he podido leer la cartera guardada: {e}")
            st.session_state["cartera_rows"] = []
    return st.session_state["cartera_rows"]


@st.cache_data(ttl=900, show_spinner=False)
def _held_prices(tickers: tuple) -> dict:
    from terminal import prices as P
    out = P.batch_last_prices(list(tickers))
    missing = [t for t in tickers if t not in out]
    if missing:
        mk, _ = screener.load_market()
        if mk is not None:
            m = mk.drop_duplicates("Ticker").set_index("Ticker")["Precio"]
            out.update({t: float(m[t]) for t in missing if t in m.index and pd.notna(m[t])})
    return out


def cartera_page():
    from terminal import cartera as C
    st.markdown("<span class='subtle'>CARTERA</span>", unsafe_allow_html=True)
    st.markdown("# Mi cartera")
    explica("cartera")
    rows = _load_cartera()
    st.caption(f"Almacenamiento: {storage.backend()}"
               + ("" if storage.backend() == "github" else " · ⚠ sin token de GitHub, lo que guardes aquí se pierde cuando la app se reinicia."))
    tabs = st.tabs(["Posiciones", "Movimientos", "IRPF"], key="cartera_tabs")

    try:
        res = C.process(rows)
    except Exception as e:  # noqa: BLE001
        st.error(f"Error al procesar los movimientos: {e}")
        return
    for w in res["avisos"]:
        st.warning(w)

    with tabs[0]:
        pos = res["posiciones"]
        if pos.empty:
            st.info("Aún no hay posiciones. Añade tus compras en «Movimientos» o importa el extracto de Interactive Brokers.")
        else:
            px = _held_prices(tuple(sorted(pos["Ticker"])))
            val = C.value_positions(pos, px)
            # Enlaza con tus análisis guardados
            saved = {it.get("ticker"): it.get("resumen") or {} for it in storage.list_all()}
            val["Valor estimado"] = val["Ticker"].map(lambda t: saved.get(t, {}).get("Valor estimado"))
            val["Margen de seguridad"] = val["Ticker"].map(lambda t: saved.get(t, {}).get("Margen de seguridad"))
            tot_v, tot_c = val["Valor (€)"].sum(), val["Coste total (€)"].sum()
            m = st.columns(4)
            m[0].metric("Valor de la cartera", f"{num(tot_v, 0)} €")
            m[1].metric("Coste", f"{num(tot_c, 0)} €")
            m[2].metric("Plusvalía latente", f"{num(tot_v - tot_c, 0)} €", f"{pct(tot_v / tot_c - 1)}" if tot_c else None)
            ys = C.tax_year(res, date.today().year)["resumen"]
            m[3].metric(f"Plusvalías realizadas {date.today().year}", f"{num(ys['Saldo neto (€)'], 0)} €")
            cols = ["Ticker", "Acciones", "Coste medio", "Precio actual", "Divisa", "Valor (€)", "Coste total (€)", "Plusvalía latente (€)",
                    "Rentabilidad", "Rentabilidad en €", "Peso", "Valor estimado", "Margen de seguridad", "Primera compra"]
            show_cols_table(val[cols].set_index("Ticker"), height=38 + 35 * len(val),
                            kinds={"Coste medio": "ps", "Precio actual": "ps", "Valor estimado": "ps", "Peso": "pct",
                                   "Rentabilidad": "pct", "Rentabilidad en €": "pct", "Acciones": "ps"})
            st.caption("«Rentabilidad en €» incluye el efecto del tipo de cambio. «Valor estimado» y «Margen de seguridad» salen de tus análisis "
                       "guardados (foto del día en que guardaste). Precios: último cierre.")
            pick = st.selectbox("Abrir ficha", list(val["Ticker"]), index=None, placeholder="Elige una posición…")
            if pick:
                _go_company(pick)

    with tabs[1]:
        st.caption("Una fila por operación. Tipo: Compra, Venta, Dividendo (pon el bruto en «Importe» y la retención en «Retención») "
                   "o Split (pon el factor en «Acciones», p. ej. 4 para un 4×1). Precio en la divisa de cotización; la conversión a euros "
                   "se hace sola con el tipo del BCE de cada fecha.")
        df = C.normalize(rows) if rows else pd.DataFrame(columns=C.COLUMNS)
        edited = st.data_editor(
            df, num_rows="dynamic", width="stretch", key="cartera_editor", height=420,
            column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
                           "Tipo": st.column_config.SelectboxColumn(options=C.TIPOS, required=True),
                           "Ticker": st.column_config.TextColumn(required=True),
                           "Acciones": st.column_config.NumberColumn(format="%.4f"), "Precio": st.column_config.NumberColumn(format="%.4f"),
                           "Importe": st.column_config.NumberColumn(format="%.2f", help="Solo dividendos: importe bruto"),
                           "Comisión": st.column_config.NumberColumn(format="%.2f"), "Retención": st.column_config.NumberColumn(format="%.2f"),
                           "Divisa": st.column_config.SelectboxColumn(options=["USD", "EUR", "GBP", "CHF", "CAD", "DKK", "SEK", "NOK", "JPY", "HKD"])})
        c = st.columns([1, 1, 2])
        if c[0].button("💾 Guardar movimientos", type="primary", width="stretch"):
            recs = C.to_records(C.normalize(edited.to_dict("records")))
            try:
                msg = storage.save("_CARTERA", {"movimientos": recs})
                st.session_state["cartera_rows"] = recs
                st.toast(msg)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"No se ha podido guardar: {e}")
        c[1].download_button("⬇ CSV", C.normalize(edited.to_dict("records")).to_csv(index=False).encode("utf-8"), "movimientos.csv",
                             width="stretch")
        with st.expander("Importar extracto de Interactive Brokers (CSV)"):
            st.caption("En IBKR: Informes → Extractos → Actividad → periodo → formato CSV. Se leen las secciones Trades, Dividends y Withholding Tax. "
                       "Las operaciones que ya tengas (misma fecha, ticker, tipo y acciones) no se duplican.")
            up = st.file_uploader("Extracto CSV", type=["csv"], label_visibility="collapsed")
            if up is not None:
                new, notes = C.parse_ibkr(up.getvalue().decode("utf-8-sig", errors="ignore"))
                for n in notes:
                    st.warning(n)
                cur = C.to_records(C.normalize(edited.to_dict("records")))
                seen = {(r["Fecha"], r["Ticker"], r["Tipo"], round(float(r["Acciones"] or 0), 4)) for r in cur}
                add = [r for r in new if (r["Fecha"], r["Ticker"], r["Tipo"], round(float(r["Acciones"] or 0), 4)) not in seen]
                st.write(f"{len(new)} operaciones en el extracto · {len(add)} nuevas.")
                if add and st.button(f"Añadir {len(add)} operaciones y guardar", type="primary"):
                    recs = C.to_records(C.normalize(cur + add))
                    try:
                        storage.save("_CARTERA", {"movimientos": recs})
                        st.session_state["cartera_rows"] = recs
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"No se ha podido guardar: {e}")

    with tabs[2]:
        years = sorted({d.year for d in pd.to_datetime(res["movimientos"]["Fecha"])} | {date.today().year}, reverse=True) \
            if not res["movimientos"].empty else [date.today().year]
        y = st.selectbox("Ejercicio fiscal", years)
        tx = C.tax_year(res, y)
        r = tx["resumen"]
        m = st.columns(4)
        m[0].metric("Saldo neto ganancias/pérdidas", f"{num(r['Saldo neto (€)'], 2)} €")
        m[1].metric("Ganancias", f"{num(r['Ganancias (€)'], 2)} €")
        m[2].metric("Pérdidas", f"{num(r['Pérdidas (€)'], 2)} €")
        m[3].metric("Dividendos brutos", f"{num(r['Dividendos brutos (€)'], 2)} €", f"retención {num(r['Retenciones en origen (€)'], 2)} €")
        st.markdown("## Transmisiones de acciones (FIFO)")
        if tx["ventas"].empty:
            st.info("No hay ventas en este ejercicio.")
        else:
            v = tx["ventas"].copy()
            show_cols_table(v.set_index("Ticker"), height=38 + 35 * len(v),
                            kinds={"Acciones": "ps", "Precio compra": "ps", "Precio venta": "ps", "Valor adquisición (€)": "ps",
                                   "Valor transmisión (€)": "ps", "Ganancia / pérdida (€)": "ps", "Ganancia en divisa": "ps"})
            if r["Ventas con aviso de regla de 2 meses"]:
                st.warning("Hay ventas con pérdida y recompras de la misma empresa en ±2 meses: esa pérdida no se integra este año "
                           "(art. 33.5.f LIRPF) hasta que vendas las acciones recompradas. Revísalo antes de declarar.")
        st.markdown("## Dividendos")
        if tx["dividendos"].empty:
            st.info("No hay dividendos en este ejercicio.")
        else:
            show_cols_table(tx["dividendos"].set_index("Ticker"), height=38 + 35 * len(tx["dividendos"]),
                            kinds={c: "ps" for c in tx["dividendos"].columns if c not in ("Fecha", "Divisa")})
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as xw:
            pd.Series(r).to_frame("Importe").to_excel(xw, sheet_name="Resumen")
            tx["ventas"].to_excel(xw, sheet_name="Transmisiones", index=False)
            tx["dividendos"].to_excel(xw, sheet_name="Dividendos", index=False)
            res["movimientos"].to_excel(xw, sheet_name="Movimientos", index=False)
        st.download_button(f"⬇ Excel para la declaración {y}", bio.getvalue(), f"IRPF_{y}_cartera.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("FIFO por empresa; valores en euros con el tipo de referencia del BCE de cada fecha; comisiones incluidas en adquisición "
                   "y restadas en transmisión. Es una ayuda para preparar la declaración, no asesoramiento fiscal: contrástalo con los datos "
                   "fiscales de tu bróker y con tu asesor.")
