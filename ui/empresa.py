from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import analysis as A, exam as E, financials as F, pipeline, plantilla, riesgo as R, sec, storage
from ui.ayuda import explica
from ui.common import (AMBER, BLUE, GREEN, MUTED, RED, cur, fig_layout, set_currency, fmt_cell, kv_table, money, mult, num, pct, show_cols_table,
                       show_rows_table)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _universe_options():
    uni = sec.universe()
    opts = [f"{u['ticker']} · {u['name']}" for u in uni]
    try:  # cotizadas europeas (cuentas ESEF)
        from terminal import esef
        opts += [f"{u['ticker']} · {u['name']} · {esef.COUNTRY_NAMES.get(u.get('country', ''), u.get('country', ''))}"
                 for u in esef.universe()]
    except Exception:  # noqa: BLE001
        pass
    return opts


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _load(ticker: str, n_years: int):
    meta, fin, hist = pipeline.load_company(ticker, n_years)
    return meta, fin, hist


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _filings(cik: int):
    return sec.filings(cik)


def _saved(ticker: str) -> dict:
    k = f"saved_{ticker}"
    if k not in st.session_state:
        try:
            st.session_state[k] = storage.load(ticker)
        except Exception as e:  # noqa: BLE001
            st.warning(f"No he podido leer el análisis guardado: {e}")
            st.session_state[k] = {}
    return st.session_state[k]


# ------------------------------------------------------------------ estado de los controles
def _key(T, *parts):
    return "_".join([T, *map(str, parts)])


def _widget_defaults(T: str, saved: dict, sugg: dict) -> dict:
    """Valor inicial de cada control de la ficha (de lo guardado o, si no hay, de las propuestas)."""
    D = {}
    p = A.params_from_dict(saved.get("params"))
    D[_key(T, "price")] = p.price if saved.get("precio_manual") else None
    D[_key(T, "r")] = p.r * 100
    D[_key(T, "n")] = int(p.n)
    D[_key(T, "mos")] = p.mos * 100
    D[_key(T, "glt")] = p.g_lt * 100
    D[_key(T, "ytm")] = int(p.years_to_margin)
    D[_key(T, "rdl")] = int(p.rd_life)
    D[_key(T, "accm")] = p.acciones_manual
    D[_key(T, "patr")] = p.patrimonio
    D[_key(T, "imp")] = p.importe
    D[_key(T, "deu")] = p.deuda_posicion
    D[_key(T, "fase")] = saved.get("fase") or "(propuesta)"
    for scn in A.SCENARIOS:
        for fld, _lbl, kind in A.SCENARIO_FIELDS:
            v = (saved.get("supuestos") or {}).get(scn, {}).get(fld)
            D[_key(T, "sc", scn, fld)] = (v * 100 if kind == "pct" else v) if v is not None else None
    answers = saved.get("examen") or {}
    for qid, _block, _t, opts in E.QUESTIONS:
        pts = answers.get(qid)
        if pts is None and qid in sugg:
            pts = sugg[qid][0]
        D[_key(T, qid)] = opts[pts - 1] if pts else (E.NA if pts == 0 else "—")
    D[_key(T, "tesis")] = saved.get("notas", "")
    D[_key(T, "cual_motivos")] = saved.get("cualitativo_motivos") or {}
    D[_key(T, "seguimiento")] = saved.get("seguimiento", "")
    rk = saved.get("riesgo") or {}
    tp = {**R.DEFAULT_TEST_PROBS, **(rk.get("test_probs") or {})}
    for scn in A.SCENARIOS:
        D[_key(T, "tp", scn)] = tp[scn] * 100
    prices_ = rk.get("test_prices") or R.DEFAULT_TEST_PRICES
    for i in range(3):
        D[_key(T, "tpx", i)] = prices_[i] if i < len(prices_) else None
    D[_key(T, "drop")] = (rk.get("drop", R.DEFAULT_DROP)) * 100
    D[_key(T, "ming")] = (rk.get("min_guarantee", R.DEFAULT_MIN_GUARANTEE)) * 100
    D[_key(T, "perfiles")] = rk.get("profiles") or [dict(x) for x in R.DEFAULT_PROFILES]
    surv = rk.get("supervivencia") or []
    for i, _q in enumerate(R.SURVIVAL_QUESTIONS):
        D[_key(T, "surv", i)] = surv[i] if i < len(surv) else ""
    return D


def _init_widgets(T: str, saved: dict, sugg: dict):
    """Streamlit borra el estado de los controles cuando cambias de página. Guardamos una copia aparte
    (_persist) y, si falta algún control, lo restauramos desde ahí o desde lo guardado."""
    persist = st.session_state.setdefault("_persist", {})
    D = _widget_defaults(T, saved, sugg)
    st.session_state[f"_keys_{T}"] = list(D)
    for k, v in D.items():
        if k not in st.session_state:
            st.session_state[k] = persist.get(k, v)
        else:
            # Reasignar convierte el valor del control en estado propio: así no se pierde aunque su pestaña no se dibuje.
            st.session_state[k] = st.session_state[k]


def _persist_widgets(T: str):
    persist = st.session_state.setdefault("_persist", {})
    for k in st.session_state.get(f"_keys_{T}", []):
        if k in st.session_state:
            persist[k] = st.session_state[k]


def _reset_widgets(T: str):
    persist = st.session_state.setdefault("_persist", {})
    for k in st.session_state.get(f"_keys_{T}", []):
        persist.pop(k, None)
        st.session_state.pop(k, None)


def _work_from_widgets(T: str) -> dict:
    s = st.session_state
    price = s.get(_key(T, "price"))
    params = {"r": s[_key(T, "r")] / 100, "n": int(s[_key(T, "n")]), "mos": s[_key(T, "mos")] / 100,
              "g_lt": s[_key(T, "glt")] / 100, "years_to_margin": int(s[_key(T, "ytm")]), "rd_life": int(s[_key(T, "rdl")]),
              "acciones_manual": s.get(_key(T, "accm")), "patrimonio": s.get(_key(T, "patr")), "importe": s.get(_key(T, "imp")), "deuda_posicion": s.get(_key(T, "deu")) or 0.0}
    if price:
        params["price"] = price
    sup = {}
    for scn in A.SCENARIOS:
        for fld, _lbl, kind in A.SCENARIO_FIELDS:
            v = s.get(_key(T, "sc", scn, fld))
            lp = s.get(_key(T, "scp", scn, fld))  # última propuesta mostrada en la casilla
            if v is not None and (lp is None or abs(v - lp) > 1e-6):
                sup.setdefault(scn, {})[fld] = v / 100 if kind == "pct" else v
    ans = {}
    for qid, _b, _t, opts in E.QUESTIONS:
        v = s.get(_key(T, qid))
        if v in opts:
            ans[qid] = opts.index(v) + 1
        elif v == E.NA:
            ans[qid] = 0
    fase = s.get(_key(T, "fase"))
    return {"params": params, "precio_manual": bool(price), "supuestos": sup, "examen": ans,
            "fase": None if fase in (None, "(propuesta)") else fase,
            "notas": s.get(_key(T, "tesis"), ""), "seguimiento": s.get(_key(T, "seguimiento"), ""),
            "riesgo": _risk_inputs(T), "cualitativo_motivos": s.get(_key(T, "cual_motivos"), {})}


def _risk_inputs(T: str) -> dict:
    s = st.session_state
    return {"test_probs": {scn: (s.get(_key(T, "tp", scn)) or 0) / 100 for scn in A.SCENARIOS},
            "test_prices": [s.get(_key(T, "tpx", i)) for i in range(3) if s.get(_key(T, "tpx", i))],
            "drop": (s.get(_key(T, "drop")) or 0) / 100, "min_guarantee": (s.get(_key(T, "ming")) or 0) / 100,
            "profiles": s.get(_key(T, "perfiles")) or [],
            "supervivencia": [s.get(_key(T, "surv", i), "") for i in range(len(R.SURVIVAL_QUESTIONS))]}


def _corto(nombre: str) -> str:
    n = nombre.split(",")[0].strip()
    return n if len(n) <= 26 else n[:25].rstrip() + "…"


# ------------------------------------------------------------------ página
def page():
    st.markdown("<span class='subtle'>FICHA DE EMPRESA</span>", unsafe_allow_html=True)
    from ui import buscador
    mis = buscador.mis_tickers()
    tickers, fmt = buscador.opciones(mis)
    # «ticker» va en la dirección (…/empresa?ticker=RMS.PA): al recargar la página sigue la misma empresa,
    # y los enlaces de las listas y del screener la abren directamente.
    qt = (st.query_params.get("ticker") or "").strip().upper()
    if qt and qt != st.session_state.get("_qt_visto"):  # enlace o recarga con ?ticker=…
        st.session_state["_qt_visto"] = qt
        st.session_state["ficha_t"] = qt
    cur_t = st.session_state.get("ficha_t")
    if cur_t and cur_t not in tickers:
        tickers = [cur_t] + tickers
    c1, c2 = st.columns([4, 1])
    T = c1.selectbox("Empresa", tickers, index=None, key="ficha_t", persist_state="session", format_func=fmt,
                     label_visibility="collapsed",
                     placeholder="🔎 Escribe el nombre o el ticker (p. ej. «hermes», «AAPL», «copart»)…",
                     help="Busca por nombre o ticker. ★ = en tus listas; el resto, de mayor a menor capitalización.")
    n_years = c2.selectbox("Años", [10, 12, 15], index=0, label_visibility="collapsed", format_func=lambda x: f"{x} años")
    rec = [t for t in st.session_state.get("_recientes", []) if t != T][:8]
    if rec or mis:
        sug = rec or [t for t in mis if t != T][:8]
        kp = f"ficha_rec_{T}"

        def _ir():
            if st.session_state.get(kp):
                st.session_state["ficha_t"] = st.session_state[kp]

        st.pills("Recientes" if rec else "De tus listas", sug, selection_mode="single", key=kp, on_change=_ir,
                 format_func=lambda t: _corto(fmt(t).replace("★ ", "").split(" · ")[0]) + f" ({t})", label_visibility="collapsed")
    if not T:
        st.info("Elige una empresa en el buscador, o vuelve a **Inicio** para ver tus listas.")
        return
    if T != qt:  # la empresa abierta queda en la dirección: al recargar sigue aquí
        st.query_params["ticker"] = T
        st.session_state["_qt_visto"] = T
    st.session_state["ticker"] = T
    st.session_state["_recientes"] = [T] + [t for t in st.session_state.get("_recientes", []) if t != T][:15]

    from terminal.esef import is_european
    eu = is_european(T)
    with st.spinner(f"Descargando {T} " + ("(informes ESEF, la primera vez tarda un poco)…" if eu else "de la SEC…")):
        try:
            meta, fin, hist = _load(T, n_years)
        except Exception as e:  # noqa: BLE001
            st.error(f"No he podido cargar {T}: {e}")
            return
    if not fin.years:
        st.error("No hay estados anuales en XBRL para esta empresa (p. ej. emisores sin etiquetar, SPACs, fondos).")
        return
    set_currency(fin.currency)

    saved = _saved(T)
    stats0 = A.history_stats(fin)
    sugg0 = E.suggestions(fin, stats0)
    _init_widgets(T, saved, sugg0)
    work = _work_from_widgets(T)
    _persist_widgets(T)
    ca = pipeline.analyze(meta, fin, hist, saved=work, auto_financial_answers=False)
    if not ca.params.price:
        st.warning("No he podido obtener la cotización. Escribe el precio a mano en «Escenarios y valoración» para valorar.")

    _header(ca)
    if saved and not st.session_state.get(f"od_sync_{T}"):  # informe de OneDrive al día (en segundo plano, una vez por sesión)
        st.session_state[f"od_sync_{T}"] = True
        try:
            from terminal import sync_onedrive
            sync_onedrive.sync_async(T)
        except Exception:  # noqa: BLE001
            pass
    _save_bar(T, work, ca)

    def _cual():
        from ui import cualitativo
        cualitativo.tab(T, ca, ca.answers, st.session_state.get(_key(T, "cual_motivos"), {}) or {})

    def _guias():
        from ui import guias
        explica("guias")
        guias.tab(T, ca)

    def _mod(name, *args):
        import importlib
        return lambda: importlib.import_module(f"ui.{name}").tab(*args)

    # Dos niveles: primero el grupo (datos → análisis → valoración → propiedad y fuentes) y dentro, sus pestañas.
    # Solo se dibuja la pestaña abierta (más rápido) y cada grupo recuerda la suya.
    grupos = {
        ":material/bar_chart: Datos": [
            (":material/dashboard: Resumen", lambda: _tab_resumen(ca)),
            (":material/show_chart: Histórico", lambda: _tab_historico(T, ca)),
            (":material/table_chart: Estados financieros", lambda: _tab_estados(ca)),
            (":material/pie_chart: Segmentos y tiendas" if eu else ":material/pie_chart: Segmentos", _mod("segmentos", T, ca)),
            (":material/flag: Guías y resultados", _guias),
        ],
        ":material/search: Análisis": [
            (":material/checklist: Examen", lambda: _tab_examen(T, ca)),
            (":material/menu_book: Cualitativo y documentos", _cual),
            (":material/groups: Comparables", _mod("comparables", T, ca)),
            (":material/trending_up: ROIC", lambda: _tab_roic(T, ca)),
            (":material/calculate: Modelo EPS", lambda: _tab_eps(ca)),
        ],
        ":material/balance: Valoración": [
            (":material/stacked_line_chart: Bandas y sensibilidad", _mod("bandas", T, ca)),
            (":material/balance: Escenarios y valoración", lambda: _tab_escenarios(T, ca)),
            (":material/warning: Riesgo", lambda: _tab_riesgo(T, ca)),
        ],
        ":material/folder_open: Propiedad y fuentes": [
            (":material/badge: Directivos y fondos", (lambda: _eu_info("propiedad")) if eu else _mod("propiedad", T, ca)),
            ((":material/description: Informes", lambda: _tab_informes_eu(ca)) if eu
             else (":material/description: SEC", lambda: _tab_filings(ca))),
            (":material/edit_note: Notas", lambda: _tab_notas(T, ca)),
        ],
    }
    if st.session_state.get("ficha_grupo") not in grupos:
        st.session_state["ficha_grupo"] = next(iter(grupos))
    st.html(_GRUPOS_CSS)
    with st.container(key="ficha_grupos"):
        g = st.segmented_control("Sección", list(grupos), key="ficha_grupo", label_visibility="collapsed", width="stretch", required=True)
    gi = list(grupos).index(g) if g in grupos else 0
    st.html(_barra_css(gi))
    pestañas = grupos[g or next(iter(grupos))]
    tabs = st.tabs([n for n, _ in pestañas], key=f"ficha_tabs_{list(grupos).index(g) if g in grupos else 0}", on_change="rerun")
    for (n, fn), tb in zip(pestañas, tabs):
        if tb.open:
            with tb:
                fn()


# Datos (azul), Análisis (violeta), Valoración (verde), Propiedad y fuentes (naranja): texto blanco legible en todos
_GRUPO_COLORES = ["#1d4ed8", "#6d28d9", "#047857", "#c2410c"]
_GRUPO_DEGRADADOS = [("#1e3a8a", "#2563eb"), ("#4c1d95", "#7c3aed"), ("#064e3b", "#059669"), ("#9a3412", "#ea580c")]


def _barra_css(gi: int) -> str:
    """Barra de pestañas del grupo abierto: a todo el ancho, degradado del color del grupo y texto blanco.
    Solo la barra principal (selectores hijo directo): las pestañas anidadas solo toman el color del grupo."""
    a, b = _GRUPO_DEGRADADOS[gi]
    k = f".st-key-ficha_tabs_{gi} > div > [role='tablist']"
    return (
        "<style>"
        f"{k}{{display:flex;width:100%;background:linear-gradient(90deg,{a},{b});border-radius:10px;padding:4px;gap:4px;"
        "box-shadow:0 2px 8px rgba(0,0,0,.12);border:none}"
        f"{k} > [role='tab']{{flex:1 1 0;justify-content:center;text-align:center;border-radius:7px;padding:.5rem .6rem;"
        "margin:0;transition:background .15s}"
        f"{k} > [role='tab'] p, {k} > [role='tab'] span{{color:rgba(255,255,255,.85) !important;font-weight:500}}"
        f"{k} > [role='tab']:hover{{background:rgba(255,255,255,.12)}}"
        f"{k} > [role='tab'][aria-selected='true']{{background:rgba(255,255,255,.24);box-shadow:inset 0 -3px 0 #fff}}"
        f"{k} > [role='tab'][aria-selected='true'] p, {k} > [role='tab'][aria-selected='true'] span"
        "{color:#fff !important;font-weight:700}"
        f"{k} .react-aria-SelectionIndicator{{display:none}}"
        f".stTabs [role='tab'][aria-selected='true'] p{{color:{_GRUPO_COLORES[gi]}}}"
        f".stTabs .react-aria-SelectionIndicator{{background-color:{_GRUPO_COLORES[gi]} !important}}"
        "</style>"
    )
_GRUPOS_CSS = "<style>" + "".join(
    f".st-key-ficha_grupos [data-testid='stButtonGroup'] button:nth-of-type({i + 1}){{"
    f"background:linear-gradient(90deg,{a},{b}) !important;border-color:{a} !important;opacity:.45;transition:all .15s}}"
    f".st-key-ficha_grupos [data-testid='stButtonGroup'] button:nth-of-type({i + 1}):hover{{opacity:.85}}"
    for i, (a, b) in enumerate(_GRUPO_DEGRADADOS)
) + (
    ".st-key-ficha_grupos [data-testid='stButtonGroup'] button{color:#fff !important;font-weight:600;"
    "border-radius:10px !important;margin:0 3px;padding:.55rem .8rem;flex:1 1 0}"
    ".st-key-ficha_grupos [data-testid='stButtonGroup'] button *{color:#fff !important}"
    ".st-key-ficha_grupos [data-testid='stButtonGroup'] button[aria-checked='true']{opacity:1 !important;outline:2px solid rgba(255,255,255,.9);outline-offset:-4px;"
    "box-shadow:0 3px 10px rgba(0,0,0,.25);transform:translateY(-1px)}"
    "</style>"
)


def _pais(meta: dict) -> str:
    from terminal.esef import COUNTRY_NAMES
    return COUNTRY_NAMES.get(meta.get("country", ""), meta.get("country", "") or "Europa")


def _eu_info(que: str):
    textos = {
        "segmentos": "En Europa, el desglose por segmentos va en las notas del informe anual y el formato ESEF no lo etiqueta "
                     "cifra a cifra, así que no puedo leerlo automáticamente. Lo tienes en el informe anual (pestaña «Informes») "
                     "y lo podemos recoger en «Guías y resultados» desde las presentaciones de resultados.",
        "propiedad": "Las compras y ventas de directivos (formulario 4) y las carteras de los grandes fondos (13F) son registros de "
                     "la SEC: solo existen para empresas que cotizan en EE. UU. En Europa, las operaciones de directivos se publican "
                     "en cada regulador (AMF, CNMV, BaFin…) y no hay una fuente única gratuita.",
    }
    st.info(textos[que])


def _tab_informes_eu(ca):
    """Informes anuales ESEF de una empresa europea (en lugar de la pestaña SEC)."""
    from terminal import esef
    st.markdown("## Informes anuales (ESEF)")
    st.caption("Informes anuales publicados en formato ESEF, del repositorio público filings.xbrl.org. «Visor» abre el "
               "informe con las cifras etiquetadas; «Informe» abre el documento completo.")
    try:
        fl = esef.entity_filings(ca.meta["lei"])
    except Exception as e:  # noqa: BLE001
        st.error(f"No he podido leer la lista de informes: {e}")
        return
    rows = [{"Ejercicio": (f["period_end"] or "")[:4], "Publicado": (f["published"] or f["added"])[:10], "País": f["country"],
             "Visor": esef.BASE + f["viewer_url"] if f.get("viewer_url") else None,
             "Informe": esef.BASE + f["report_url"] if f.get("report_url") else None} for f in fl]
    df = pd.DataFrame(rows).sort_values("Publicado", ascending=False)
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"Visor": st.column_config.LinkColumn("Visor", display_text="Abrir visor"),
                                "Informe": st.column_config.LinkColumn("Informe", display_text="Abrir informe")})
    st.caption(f"LEI {ca.meta.get('lei')} · ISIN {ca.meta.get('isin') or '—'}. El ejercicio que muestra el repositorio a veces va "
               "desfasado un año; las cifras de la terminal usan las fechas reales de cada dato.")


def _header(ca: pipeline.CompanyAnalysis):
    f = ca.fin
    L = f.years[-1]
    eps = f.get("eps_diluted", L)
    P = ca.params.price
    shares = f.get("shares_outstanding", L) or f.get("shares_diluted", L)
    mcap = P * shares if (P and shares) else None
    st.markdown(f"<h1><span class='tick'>{f.ticker}</span>{f.name}</h1>"
                f"<span class='pill'>{ca.meta.get('exchange')}</span>"
                + (f"<span class='pill'>{_pais(ca.meta)}</span><span class='pill'>Cuentas NIIF · {f.currency}</span>"
                   if ca.meta.get("region") == "EU" else f"<span class='pill'>CIK {f.cik}</span>") +
                f"<span class='pill'>Último ejercicio {L} · cierre {f.period_end.get(L, '')}</span>"
                f"<span class='pill am'>Fase: {ca.phase}</span>", unsafe_allow_html=True)
    v = ca.val
    h = ca.hist.dropna() if ca.hist is not None else pd.Series(dtype=float)
    h1 = h[h.index >= h.index.max() - pd.DateOffset(years=1)] if len(h) else h
    ch1 = (float(h1.iloc[-1]) / float(h1.iloc[0]) - 1) if len(h1) > 20 else None
    spark_px = [round(float(x), 2) for x in h1.iloc[::5]] if len(h1) > 20 else None
    rev = [x for x in f.series("revenue") if x is not None]
    pe_hist = [round(x, 1) for x in ca.eps_df["PER"] if x is not None and x == x and 0 < x < 200] if "PER" in ca.eps_df else []
    pe_now = (P / eps) if (P and eps and eps > 0) else None
    cols = st.columns(8)
    cols[0].metric("Precio", f"{num(P, 2)} {cur()}" if P else "—", (("+" if ch1 >= 0 else "") + pct(ch1) + " 1 año") if ch1 is not None else None,
                   chart_data=spark_px, chart_type="area",
                   help=f"Última cotización ({ca.params.price_date or 'manual'}). Debajo, la variación y el gráfico del último año.")
    med = sorted(pe_hist)[len(pe_hist) // 2] if pe_hist else None
    cols[1].metric("PER", mult(pe_now), (f"mediana {mult(med)}" if med else None), delta_color="off", delta_arrow="off",
                   chart_data=(pe_hist + ([round(pe_now, 1)] if pe_now else [])) or None, chart_type="line",
                   help="Precio / BPA diluido del último ejercicio. Debajo, la mediana de los PER medios de cada año.")
    cols[2].metric("Capitalización", money(mcap) if mcap else "—", help="Precio × acciones en circulación.")
    g = (rev[-1] / rev[-2] - 1) if len(rev) >= 2 and rev[-2] else None
    cols[3].metric(f"Ventas {L}", money(f.get("revenue", L)), (("+" if g >= 0 else "") + pct(g) + " a/a") if g is not None else None,
                   chart_data=[round(x) for x in rev] or None, chart_type="bar",
                   help="Ventas del último ejercicio y su evolución en el periodo elegido.")
    sc = ca.score
    cols[4].metric("Nota (examen)", (num(sc["final"], 2) if sc["cual_respondidas"] else num(sc["financiera"], 2) + "*") + " / 10",
                   f"{sc['respondidas']}/{sc['total']} resp." if sc["cual_respondidas"] else "*solo financiera",
                   delta_color="off", delta_arrow="off",
                   help="Nota del examen (0–10). Con asterisco, solo la parte financiera automática: falta tu examen cualitativo.")
    if v and v.value:
        mos = v.value["Margen de seguridad al precio actual"]
        rent = v.value["Rentabilidad anual implícita en la media"]
        cols[5].metric("Valor estimado", f'{num(v.value["Valor estimado hoy = E[VF] / (1+r)^n"], 2)} {cur()}',
                       help="Valor por acción hoy según tus escenarios (pestaña «Escenarios y valoración»).")
        cols[6].metric("Margen seg.", pct(mos), "a favor" if (mos or 0) > 0 else "en contra",
                       delta_color="normal" if (mos or 0) > 0 else "inverse", delta_arrow="off",
                       help="Cuánto por debajo del valor estimado cotiza. Positivo = cotiza por debajo del valor.")
        cols[7].metric("Veredicto", v.coverage.get("Veredicto", "—"), f"{pct(rent)} al año", delta_arrow="off",
                       delta_color="normal" if (((rent or 0) >= ca.params.r) == ((rent or 0) >= 0)) else "inverse",
                       help=f"Rentabilidad anual implícita al precio actual. Verde si supera la que exiges ({pct(ca.params.r)}).")
    for w in f.warnings + ((v.warnings if v else [])):
        st.caption(f"⚠ {w}")


def _save_bar(T, work, ca):
    c1, c2, c4, c3 = st.columns([1, 1, 1, 1.6])
    from ui.prioridad import selector_lista
    lc = st.columns([0.55, 5])
    lc[0].markdown("<div class='subtle' style='padding-top:.45rem'>Mis listas:</div>", unsafe_allow_html=True)
    selector_lista(T, lc[1])
    if c4.button("↺ Volver a lo guardado", width="stretch", help="Descarta los cambios sin guardar de esta empresa."):
        _reset_widgets(T)
        st.session_state.pop(f"saved_{T}", None)
        st.rerun()
    if c1.button("💾 Guardar análisis", type="primary", width="stretch"):
        data = dict(work)
        data["resumen"] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in pipeline.summary_row(ca).items()}
        try:  # conserva lo que se guarda desde otras pestañas (p. ej. el dossier)
            prev = storage.load(T) or {}
            for k, v in prev.items():  # dossier, guías, comparables, bitácora…
                if k not in data:
                    data[k] = v
        except Exception:  # noqa: BLE001
            pass
        try:
            msg = storage.save(T, data)
            st.session_state[f"saved_{T}"] = data
            st.toast(msg)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se ha podido guardar: {e}")
    try:
        xls = plantilla.build_workbook(ca, work)
        c2.download_button("⬇ Excel (mi plantilla)", data=xls, file_name=f"{T} - analisis financer {date.today().year}.xlsx", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           help="Tu plantilla de Excel con los datos de esta empresa, tus supuestos y el examen nuevo. Excel recalcula al abrir.")
    except Exception as e:  # noqa: BLE001
        c2.download_button("⬇ Excel (datos)", data=_excel(ca), file_name=f"{T}_analisis.xlsx", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", help=f"Plantilla no disponible: {e}")
    c3.markdown(f"<span class='subtle'>Guardado en: {storage.backend()} · último: {_saved(T).get('actualizado', 'nunca')}</span>",
                unsafe_allow_html=True)


# ------------------------------------------------------------------ pestañas
def _tab_resumen(ca):
    explica("resumen")
    f = ca.fin
    ys = [str(y) for y in f.years]
    eps_df = ca.eps_df
    c1, c2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=ys, y=f.series("revenue"), name="Ventas", marker_color=BLUE, hovertemplate="%{y:,.0f} M" + cur())
    fig.add_bar(x=ys, y=f.series("net_income"), name="Beneficio neto", marker_color=AMBER, hovertemplate="%{y:,.0f} M" + cur())
    fig.add_bar(x=ys, y=f.series("fcf"), name="Flujo de caja libre", marker_color=GREEN, hovertemplate="%{y:,.0f} M" + cur())
    fig.update_yaxes(tickformat=",.0f")
    c1.plotly_chart(fig_layout(fig, "Ventas, beneficio y caja libre", unit=f"millones de {cur()}"), width="stretch")
    eps = f.series("eps_diluted")
    fig = go.Figure()
    fig.add_bar(x=ys, y=eps, name="BPA diluido", marker_color=[BLUE if (e or 0) >= 0 else RED for e in eps],
                hovertemplate="%{y:,.2f} " + cur() + "<extra>BPA</extra>", text=[num(e, 2) for e in eps], textposition="outside", cliponaxis=False,
                textfont=dict(size=10, color=MUTED))
    fig.update_layout(showlegend=False)
    c2.plotly_chart(fig_layout(fig, "Beneficio por acción (BPA diluido)", unit=f"{cur()} por acción"), width="stretch")

    c3, c4 = st.columns(2)
    per = [p if (p is not None and p == p and 0 < p < 200) else None for p in eps_df["PER"]] if "PER" in eps_df else []
    fig = go.Figure()
    if any(p is not None for p in per):
        vals = sorted(p for p in per if p is not None)
        med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        fig.add_scatter(x=ys, y=per, name="PER medio del año", mode="lines+markers", line=dict(color=BLUE, width=2), marker=dict(size=8),
                        hovertemplate="%{y:,.1f}x<extra>PER</extra>", connectgaps=False)
        fig.add_hline(y=med, line_dash="dash", line_color=MUTED, line_width=1,
                      annotation_text=f"mediana {mult(med)}", annotation_position="top left", annotation_font_color=MUTED)
        P, e0 = ca.params.price, eps[-1] if eps else None
        if P and e0 and e0 > 0:
            fig.add_scatter(x=[ys[-1]], y=[P / e0], name="PER hoy", mode="markers", marker=dict(size=12, color=AMBER, symbol="diamond",
                            line=dict(color="#ffffff", width=2)), hovertemplate="%{y:,.1f}x<extra>PER hoy</extra>")
        fig.update_yaxes(ticksuffix="x", rangemode="tozero")
    else:
        fig.add_annotation(text="Sin precios históricos para calcular el PER", showarrow=False, font=dict(color=MUTED))
    c3.plotly_chart(fig_layout(fig, "PER histórico: ¿cara o barata frente a sí misma?", unit="veces beneficio"), width="stretch")
    fig = go.Figure()
    for k, name, col in [("gm_series", "Margen bruto", BLUE), ("om_series", "Margen operativo", AMBER)]:
        s_ = ca.stats[k]
        fig.add_scatter(x=[str(y) for y in s_], y=list(s_.values()), name=name, mode="lines+markers", line=dict(color=col, width=2),
                        hovertemplate="%{y:.1%}")
    nm = [(n / r) if (n is not None and r) else None for n, r in zip(f.series("net_income"), f.series("revenue"))]
    fig.add_scatter(x=ys, y=nm, name="Margen neto", mode="lines+markers", line=dict(color=GREEN, width=2), hovertemplate="%{y:.1%}")
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    c4.plotly_chart(fig_layout(fig, "Márgenes", unit="% de las ventas"), width="stretch")

    c5, c6 = st.columns(2)
    fig = go.Figure()
    r = ca.roic_df
    fig.add_scatter(x=ys, y=list(r.loc["ROIC"]), name="ROIC", mode="lines+markers", line=dict(color=BLUE, width=2), hovertemplate="%{y:.1%}")
    fig.add_scatter(x=ys, y=list(r.loc["ROIC ajustado (I+D capitalizado)"]), name="ROIC ajustado I+D", mode="lines+markers",
                    line=dict(color=AMBER, width=2), hovertemplate="%{y:.1%}")
    fig.add_scatter(x=ys, y=list(eps_df["ROE"]), name="ROE", mode="lines+markers", line=dict(color=GREEN, width=2, dash="dot"),
                    hovertemplate="%{y:.1%}")
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    c5.plotly_chart(fig_layout(fig, "Rentabilidad del capital", unit="% anual"), width="stretch")
    sh = f.series("shares_diluted")
    fig = go.Figure()
    fig.add_bar(x=ys, y=sh, name="Acciones diluidas", marker_color=MUTED, hovertemplate="%{y:,.0f} M<extra>Acciones</extra>")
    shv = [x for x in sh if x]
    if len(shv) >= 2:
        chg = shv[-1] / shv[0] - 1
        fig.add_annotation(text=f"{'−' if chg < 0 else '+'}{pct(abs(chg))} en el periodo · {'recompra' if chg < 0 else 'dilución'}",
                           xref="paper", yref="paper", x=1, y=1.08, showarrow=False, xanchor="right",
                           font=dict(color=(GREEN if chg < 0 else RED), size=12))
        fig.update_yaxes(range=[min(shv) * 0.85, max(shv) * 1.05])
    fig.update_layout(showlegend=False)
    c6.plotly_chart(fig_layout(fig, "Acciones en circulación (diluidas)", unit="millones"), width="stretch")

    st.markdown("## Lo primero que miras")
    s = ca.stats
    L = f.years[-1]
    eps = f.series("eps_diluted")
    eps_up = sum(1 for a, b in zip(eps, eps[1:]) if a is not None and b is not None and b > a)
    cols = st.columns(5)
    cols[0].metric("Ventas: crecimiento 3a / 5a", f"{pct(s['g3'])} / {pct(s['g5'])}", f"{s['years_down']} años con caída")
    cols[1].metric("BPA: años al alza", f"{eps_up}/{len(eps) - 1}", f"CAGR {pct(A._cagr(eps[-1], eps[0], len(eps) - 1))}")
    P = ca.params.price
    cols[2].metric("PER actual vs histórico", mult(P / f.get('eps_diluted', L) if P and (f.get('eps_diluted', L) or 0) > 0 else None),
                   f"medio {mult(A.per_history(eps_df)['PER sin outliers'])} (sin outliers)")
    cols[3].metric("Margen operativo", pct(s["om_last"]), f"medio 5a {pct(s['om5'])}")
    cols[4].metric("ROIC último año", pct(ca.roic_df.loc['ROIC'].iloc[-1]), f"ajustado I+D {pct(ca.roic_df.loc['ROIC ajustado (I+D capitalizado)'].iloc[-1])}")
    st.caption("La ventaja competitiva no sale de los datos: va en el examen cualitativo y en tus notas.")


HIST_METRICS = [
    ("Ventas", "revenue", "m"), ("Beneficio neto", "net_income", "m"), ("BPA diluido", "eps_diluted", "ps"),
    ("Flujo de caja libre", "fcf", "m"), ("Flujo de caja operativo", "ocf", "m"), ("EBITDA", "ebitda", "m"),
    ("Resultado operativo", "operating_income", "m"), ("Margen bruto", "_gm", "pct"), ("Margen operativo", "_om", "pct"),
    ("Margen neto", "_nm", "pct"), ("ROE", "_roe", "pct"), ("ROIC", "_roic", "pct"), ("PER (precio medio)", "_per", "x"),
    ("Acciones diluidas (M)", "shares_diluted", "m"), ("Valor contable por acción", "_bvps", "ps"), ("Dividendo por acción", "_dps", "ps"),
    ("Caja e inversiones a corto", "cash_sti", "m"), ("Deuda a largo plazo", "lt_debt", "m"), ("Patrimonio neto", "equity", "m"),
    ("I+D", "rnd", "m"), ("Remuneración en acciones", "sbc", "m"), ("Recompras brutas", "buybacks", "m"),
]


def _hist_series(ca, key):
    f, e = ca.fin, ca.eps_df
    if key == "_gm":
        return [ca.stats["gm_series"].get(y) for y in f.years]
    if key == "_om":
        return [ca.stats["om_series"].get(y) for y in f.years]
    if key == "_nm":
        return list(e["Margen neto"])
    if key == "_roe":
        return list(e["ROE"])
    if key == "_roic":
        return list(ca.roic_df.loc["ROIC"])
    if key == "_per":
        return list(e["PER"])
    if key == "_bvps":
        return list(e["Valor contable por acción"])
    if key == "_dps":
        return list(e["Dividendo por acción"])
    return f.series(key)


def _tab_historico(T, ca):
    explica("historico")
    from ui import historico
    historico.tab(T, ca, _key)


def _tab_examen(T, ca):
    explica("examen")
    sc = ca.score
    cols = st.columns(4)
    cols[0].metric("Nota final", f"{sc['final']:.2f}")
    cols[1].metric("Cualitativa", f"{sc['cualitativa']:.2f}", f"{sc['cual_respondidas']}/20 respondidas")
    cols[2].metric("Financiera", f"{sc['financiera']:.2f}")
    cols[3].metric("Nota / 10 (Modelo EPS)", f"{sc['final'] / 10:.3f}")
    st.caption("Las respuestas financieras vienen propuestas con 10 años de datos y criterios de Buffett (debajo de cada una ves el cálculo). "
               "Cámbialas si no estás de acuerdo. Sin responder = 0 puntos, como en tu Excel; «No aplica» no cuenta en la media del bloque.")
    na_fin = sum(sc["blocks"][b]["na"] for b in E.FINANCIAL_BLOCKS)
    if na_fin >= 6:
        st.warning(f"{na_fin} de 21 preguntas financieras están en «No aplica» (típico de bancos y aseguradoras): "
                   "la nota financiera se apoya en pocas métricas, úsala con cautela.")
    with st.expander("🤖 Rellenar el bloque cualitativo con Claude (usa tu plan, no la API)", expanded=not sc["cual_respondidas"]):
        st.markdown("1. Copia este texto (botón de copiar arriba a la derecha) y pégalo en un chat nuevo de Claude con la búsqueda web activada.\n"
                    "2. Cuando conteste, copia toda su respuesta y pégala abajo.\n"
                    "3. Pulsa **Rellenar**. Revisa cada respuesta: son una propuesta, la decisión es tuya.")
        st.code(E.claude_prompt(ca.fin, ca.stats, st.session_state.get(_key(T, "tesis"), "")), language=None)
        pasted = st.text_area("Respuesta de Claude", key=_key(T, "claude_paste"), height=140,
                              placeholder="Pega aquí la respuesta completa (debe acabar con el bloque JSON)…")
        if st.button("Rellenar el cualitativo", type="primary", disabled=not pasted):
            answers, reasons, warns = E.parse_claude_answer(pasted)
            for w in warns:
                st.warning(w)
            if answers:
                for qid, pts in answers.items():
                    st.session_state[_key(T, qid)] = E.Q[qid][3][pts - 1]
                st.session_state[_key(T, "cual_motivos")] = {**st.session_state.get(_key(T, "cual_motivos"), {}), **reasons}
                st.toast(f"{len(answers)} respuestas cualitativas rellenadas. Recuerda pulsar «Guardar análisis».")
                st.rerun()
    motivos = st.session_state.get(_key(T, "cual_motivos"), {}) or {}
    blocks = E.QUALITATIVE_BLOCKS + E.FINANCIAL_BLOCKS
    left, right = st.columns(2)
    for i, b in enumerate(blocks):
        col = left if b in E.QUALITATIVE_BLOCKS else right
        with col:
            nb = sc["blocks"][b]
            sub = E.BLOCK_SUBTITLE.get(b, "")
            nota_txt = "n.a." if nb["nota"] is None else f"{nb['nota']:.2f}"
            st.markdown(f"### {b} <span class='subtle'>{sub}</span> <span class='pill am'>{nota_txt}</span>", unsafe_allow_html=True)
            for qid, qb, text, opts in E.QUESTIONS:
                if qb != b:
                    continue
                choices = ["—"] + opts + ([E.NA] if b in E.FINANCIAL_BLOCKS else [])
                if st.session_state.get(_key(T, qid)) not in choices:
                    st.session_state[_key(T, qid)] = "—"
                st.selectbox(text, choices, key=_key(T, qid), help=E.HELP.get(qid))
                if qid in motivos:
                    st.markdown(f"<div class='why'>Claude: {motivos[qid]}</div>", unsafe_allow_html=True)
                if qid in ca.suggestions:
                    pts, why = ca.suggestions[qid]
                    label = opts[pts - 1] if pts else E.NA
                    st.markdown(f"<div class='why'>Propuesta: {label} · {why}</div>", unsafe_allow_html=True)


def _tab_estados(ca):
    explica("estados")
    f = ca.fin
    ps_kinds = {F.LABELS[k]: "ps" for k in ("eps_basic", "eps_diluted")}
    m_kinds = {F.LABELS[k]: "m" for k in F.LABELS}
    m_kinds.update(ps_kinds)
    L = F.LABELS
    bold = {L[k] for k in ("revenue", "gross_profit", "operating_income", "pretax", "net_income", "ebitda", "eps_diluted",
                           "current_assets", "lt_assets", "total_assets", "current_liabilities", "lt_liabilities",
                           "total_liabilities", "equity", "liabilities_equity", "ocf", "icf", "fcf_fin", "net_cash_flow", "fcf")
            if k in L}
    indent = {L[k] for k in ("cogs", "rnd", "sga", "nonop", "taxes", "da", "shares_basic", "eps_basic",
                             "cash_sti", "receivables", "inventory", "prepaid", "other_current_assets", "ppe", "lt_investments",
                             "goodwill_intangibles", "other_lt_assets", "st_debt", "lt_debt", "other_lt_liabilities",
                             "retained_earnings", "aoci", "sbc", "chg_receivables", "chg_inventory", "chg_payables", "capex",
                             "acquisitions", "debt_net", "equity_net", "dividends") if k in L}
    st.caption("En **negrita**, las partidas clave (totales y resultados); con sangría, el detalle que las compone. Negativos en rojo.")
    for title, rows in [("Cuenta de resultados (PyG)", F.PYG_ROWS), ("Balance", F.BALANCE_ROWS), ("Cash Flow", F.CASHFLOW_ROWS)]:
        st.markdown(f"## {title}")
        df = f.table(rows)
        show_rows_table(df, kinds=m_kinds, bold=bold, indent=indent)
    st.caption(f"Millones de {f.currency}; acciones en millones. Fuente: SEC EDGAR XBRL (10-K). Fechas de cierre: "
               + ", ".join(f"{y}: {e}" for y, e in f.period_end.items()))
    with st.expander("De qué etiqueta XBRL sale cada dato"):
        rows = []
        for k, by_year in f.sources.items():
            if k.startswith("_") and not by_year:
                continue
            tags = sorted(set(by_year.values()))
            if tags:
                rows.append({"Concepto": F.LABELS.get(k, k), "Etiquetas usadas": ", ".join(tags)})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _tab_eps(ca):
    explica("eps")
    st.markdown("## Modelo EPS · histórico")
    df = ca.eps_df.copy()
    show_cols_table(df)
    if not df["Precio medio"].notna().any():
        st.caption("Sin histórico de precios: no puedo calcular el PER de cada año.")
    else:
        st.caption("Precio medio = media de los cierres diarios de cada ejercicio fiscal (ajustados por splits).")
    if ca.val:
        st.markdown("## Proyección (escenario base)")
        base = ca.val.projections["Base"]
        keep = ["BPA diluido", "Crecimiento del BPA", "Dividendo por acción", "Ventas", "Crecimiento de ventas", "Beneficio neto",
                "Margen neto %", "Acciones diluidas (M)", "Valor contable por acción", "ROE"]
        show_rows_table(base.loc[keep], kinds={"Ventas": "m", "Beneficio neto": "m", "Acciones diluidas (M)": "m"},
                        bold={"BPA diluido", "Ventas", "Beneficio neto"})
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("## Control histórico del PER")
        kv_table(A.per_history(ca.eps_df))
    with c2:
        st.markdown("## Buffettología (tu modelo original)")
        b = A.buffettology(ca.fin, ca.stats, ca.eps_df, ca.params.price)
        if b:
            kv_table({k: v for k, v in b.items()})
        else:
            st.caption("No aplicable (patrimonio negativo o sin datos).")


def _tab_roic(T, ca):
    explica("roic")
    st.number_input("Vida útil del I+D capitalizado (años)", 1, 10, key=_key(T, "rdl"))
    st.markdown("## ROIC y capital invertido")
    st.caption("Capital invertido = deuda a largo plazo + patrimonio neto − caja e inversiones a corto. NOPAT = EBIT × (1 − tipo efectivo).")
    show_rows_table(ca.roic_df, kinds={"Crecimiento del NOPAT ($)": "m", "Gasto en I+D": "m", "EBIT": "m", "EBIT ajustado": "m",
                                       "NOPAT": "m", "NOPAT ajustado": "m", "Activo de I+D capitalizado": "m",
                                       "Amortización del I+D capitalizado": "m", "Ajuste al EBIT": "m"}, bold={"Capital invertido (fin de año)", "NOPAT", "ROIC", "ROIC incremental", "ROIC ajustado (I+D capitalizado)"})


def _tab_escenarios(T, ca):
    st.markdown("## 1. Parámetros del inversor")
    explica("esc_1")
    c = st.columns(7)
    c[0].number_input("Precio (vacío = mercado)", min_value=0.0, step=1.0, key=_key(T, "price"), placeholder=num(ca.params.price, 2))
    c[1].number_input("Rentabilidad exigida r (%)", 0.0, 50.0, step=0.5, key=_key(T, "r"))
    c[2].number_input("Horizonte n (años)", 1, 10, key=_key(T, "n"))
    c[3].number_input("Margen de seguridad (%)", 0.0, 90.0, step=1.0, key=_key(T, "mos"))
    c[4].number_input("Crecimiento LP / PIB (%)", -5.0, 15.0, step=0.5, key=_key(T, "glt"))
    c[5].number_input("Años hasta márgenes", 1, 10, key=_key(T, "ytm"))
    c[6].selectbox("Fase", ["(propuesta)"] + A.PHASES, key=_key(T, "fase"))
    if ca.fin.sources.get("eps_diluted") == {} or ca.params.acciones_manual:
        st.number_input("La SEC no da BPA de esta empresa (suele pasar con varias clases de acciones). Acciones diluidas en millones, as-converted:",
                        min_value=0.0, step=1.0, key=_key(T, "accm"))
    st.caption(f"Fase propuesta: **{ca.stats['phase']}** · Fase usada: **{ca.phase}**. El PER pagado hoy es "
               f"{mult(ca.params.price / ca.fin.get('eps_diluted', ca.fin.years[-1]) if ca.params.price and (ca.fin.get('eps_diluted', ca.fin.years[-1]) or 0) > 0 else None)}.")

    with st.expander("2. Histórico y fase de la empresa", expanded=False):
        rows = []
        for k, lbl, kind in A.STAT_LABELS:
            v = ca.stats.get(k)
            rows.append((lbl, "Sí" if v is True else "No" if v is False else fmt_cell(v, {"pct": "pct", "int": "m"}.get(kind, "m")) if not isinstance(v, str) else v))
        st.dataframe(pd.DataFrame(rows, columns=["", "Valor"]).set_index(""), width="stretch", height=600)

    st.markdown("## 3. Escenarios")
    explica("esc_3")
    st.caption("Cada casilla trae la propuesta según la fase (tu Excel). Escribe encima para fijar tu supuesto; si no la tocas, sigue a la propuesta "
               "cuando cambies la fase, r o el crecimiento del año 10. Porcentajes en %.")
    if st.button("↺ Volver a las propuestas en todos los escenarios", key=_key(T, "sc_reset")):
        for scn in A.SCENARIOS:
            for fld, _l, _k in A.SCENARIO_FIELDS:
                st.session_state[_key(T, "sc", scn, fld)] = None
                st.session_state.pop(_key(T, "scp", scn, fld), None)
        st.rerun()
    # Sincroniza las casillas que no has tocado con la propuesta actual
    props = {}
    for scn in A.SCENARIOS:
        for fld, _lbl, kind in A.SCENARIO_FIELDS:
            prop = ca.proposed[scn][fld] if fld != "per_exit" else A.exit_per(ca.scenarios[scn]["g10"], ca.params.r, ca.stats.get("roe5"))
            p_ui = prop * 100 if kind == "pct" else prop
            props[(scn, fld)] = p_ui
            k, kp = _key(T, "sc", scn, fld), _key(T, "scp", scn, fld)
            vcur, lp = st.session_state.get(k), st.session_state.get(kp)
            if vcur is None or (lp is not None and abs(vcur - lp) <= 1e-6):
                st.session_state[k] = p_ui
                st.session_state[kp] = p_ui
            elif lp is None:
                st.session_state[kp] = p_ui
    head = st.columns([2.2, 1, 1, 1, 1])
    head[0].markdown("<span class='subtle'>Supuesto</span>", unsafe_allow_html=True)
    for i, scn in enumerate(A.SCENARIOS):
        head[i + 1].markdown(f"**{scn}**")
    mine = []
    for fld, lbl, kind in A.SCENARIO_FIELDS:
        row = st.columns([2.2, 1, 1, 1, 1])
        row[0].markdown(f"<div style='padding-top:.45rem'>{lbl}</div>", unsafe_allow_html=True)
        for i, scn in enumerate(A.SCENARIOS):
            row[i + 1].number_input(lbl, step=0.5, format="%.2f", key=_key(T, "sc", scn, fld), label_visibility="collapsed")
            vcur = st.session_state.get(_key(T, "sc", scn, fld))
            if vcur is not None and abs(vcur - props[(scn, fld)]) > 1e-6:
                mine.append(f"{scn} · {lbl}: **{vcur:.2f}** (propuesta {props[(scn, fld)]:.2f})")
    if mine:
        st.markdown("<span class='pill am'>Tus supuestos</span> " + " · ".join(mine), unsafe_allow_html=True)
    with st.expander("¿De dónde sale el PER de salida?"):
        r_ = ca.params.r
        roe5 = ca.stats.get("roe5") or 0.0
        rows = []
        for scn in A.SCENARIOS:
            g10 = ca.scenarios[scn]["g10"]
            g = min(g10, r_ - 0.03)
            roe = max(roe5, r_ + 0.01)
            just = A.exit_per(g10, r_, ca.stats.get("roe5"))
            rows.append({"Escenario": scn, "Crecimiento año 10": f"{g10:.1%}", "g usado = mín(g10, r − 3 pp)": f"{g:.1%}",
                         "ROE usado = máx(ROE 5 años, r + 1 pp)": f"{roe:.1%}", "r": f"{r_:.1%}", "PER justificado": f"{just:.1f}x",
                         "PER que se usa": f"{ca.scenarios[scn]['per_exit']:.1f}x"})
        st.dataframe(pd.DataFrame(rows).set_index("Escenario"), width="stretch")
        ph = A.per_history(ca.eps_df)
        eps0 = ca.fin.get("eps_diluted", ca.fin.years[-1])
        st.markdown(
            "Es la fórmula de tu Excel: el **PER «justificado» por fundamentales** que pagaría un comprador racional en el año 10:\n\n"
            "**PER = (1 − g / ROE) × (1 + g) / (r − g)**, con un mínimo de 5x.\n\n"
            "- **g**: el crecimiento que la empresa mantendrá después del año 10 (el del año 10 del escenario, limitado a r − 3 pp para que la fórmula no se dispare).\n"
            "- **ROE**: lo que rinde el beneficio que reinvierte; con un ROE alto necesita retener poco para crecer y puede repartir más, por eso vale más.\n"
            "- **r**: tu rentabilidad exigida. Cuanto más exiges, menos pagas.\n\n"
            f"Como referencia: PER pagado hoy **{(ca.params.price / eps0) if (ca.params.price and eps0 and eps0 > 0) else float('nan'):.1f}x**, "
            f"PER histórico medio sin extremos **{(ph['PER sin outliers'] or float('nan')):.1f}x**, mínimo histórico **{(ph['PER mínimo'] or float('nan')):.1f}x**. "
            "Si crees que la ventaja competitiva seguirá en el año 10 y el mercado pagará más (o menos), escribe tu PER en la casilla.")
    psum = sum(ca.scenarios[s]["prob"] for s in A.SCENARIOS)
    st.markdown(f"<span class='pill {'ok' if abs(psum - 1) < 1e-4 else 'ko'}'>Suma de probabilidades: {psum:.0%}</span>", unsafe_allow_html=True)

    v = ca.val
    if not v:
        st.info("Necesito un precio y un BPA para valorar.")
        return
    st.markdown("## 4. Valor futuro por escenario")
    explica("esc_4")
    show_rows_table(v.by_scenario, bold={"Valor futuro (VF)", "Rentabilidad anual", "Probabilidad"})
    st.markdown("## 5. Test de cobertura · 6. Valor estimado y margen de seguridad")
    explica("esc_56")
    c1, c2 = st.columns(2)
    with c1:
        kv_table(v.coverage)
    with c2:
        kv_table(v.value)
    fig = go.Figure()
    U = v.coverage["Umbral P·(1+r)^n"]
    vf = v.by_scenario.loc["Valor futuro (VF)"]
    fig.add_bar(x=list(vf.index), y=list(vf.values), marker_color=[GREEN if x >= U else RED for x in vf.values],
                text=[f"{x:,.0f}<br>p={p:.0%}" for x, p in zip(vf.values, v.by_scenario.loc["Probabilidad"])], textposition="outside")
    fig.add_hline(y=U, line_dash="dash", line_color=AMBER, annotation_text=f"Umbral {U:,.0f}", annotation_font_color=AMBER)
    fig.add_hline(y=v.coverage["Valor futuro esperado E[VF]"], line_dash="dot", line_color=BLUE, annotation_text="E[VF]", annotation_font_color=BLUE)
    st.plotly_chart(fig_layout(fig, f"Valor futuro en el año {ca.params.n} frente al umbral", 340, unit=f"{cur()} por acción"), width="stretch")

    st.markdown("## 7. Ventana de horizontes (escenario base)")
    explica("esc_7")
    show_rows_table(v.window, kinds={"Caja acumulada por acción C(n)": "ps", "Dividendos capitalizados D(n)": "ps"})
    st.caption("Múltiplo requerido = (P·(1+r)^n − D(n) − C(n)) / B(n). La ventana son los años en que no supera la referencia.")

    st.markdown("## 8. Test de exposición (opcional)")
    explica("esc_8")
    c = st.columns(3)
    c[0].number_input("Patrimonio líquido", min_value=0.0, step=1000.0, key=_key(T, "patr"))
    c[1].number_input("Importe invertido en la posición", min_value=0.0, step=1000.0, key=_key(T, "imp"))
    c[2].number_input("Deuda ligada a la posición", min_value=0.0, step=1000.0, key=_key(T, "deu"))
    if v.exposure is not None:
        show_rows_table(v.exposure, kinds={"Valor final de la posición": "m", "Capital propio tras devolver la deuda": "m"})
    st.markdown("<div class='subtle'>¿Quién puede obligarme a vender? ¿Qué tendría que ocurrir para que lo hiciera? · ¿Hay deuda ligada al valor de la posición? "
                "· ¿Necesitaré este dinero antes del horizonte? ¿Pueden fallar mis otras fuentes de liquidez a la vez?</div>", unsafe_allow_html=True)

    st.markdown("## Proyecciones completas")
    for scn in A.SCENARIOS:
        with st.expander(f"Proyección · {scn}"):
            df = v.projections[scn]
            show_rows_table(df, kinds={"Margen bruto": "m", "Variación del circulante": "m", "Variación de caja": "m",
                                       "Variación de deuda": "m", "Acciones diluidas (M)": "m"},
                            bold={"Ventas", "Resultado operativo (EBIT)", "Beneficio neto", "BPA diluido", "Flujo de caja libre",
                                  "Total activo", "Patrimonio neto", "— FLUJO DE CAJA —", "— BALANCE —"},
                            indent={"   de los cuales I+D", "   comerciales, generales y otros"})


def _tab_riesgo(T, ca):
    explica("riesgo")
    v = ca.val
    if not v:
        st.info("Necesito un precio y un BPA para el análisis de riesgo.")
        return
    rin = _risk_inputs(T)
    rr = R.analyze_risk(v, ca.params, rin["test_probs"], rin["test_prices"], rin["drop"], rin["min_guarantee"], rin["profiles"])
    st.caption("Método «Parte II · El riesgo». Todo sale de «Escenarios y valoración»: cambia allí precio, r, horizonte o supuestos y esto se recalcula.")

    st.markdown("## Conclusión")
    for line in rr.conclusion:
        st.markdown(f"<div style='margin-bottom:.4rem'>{line}</div>", unsafe_allow_html=True)

    st.markdown("## Resumen BPA futuro y precio de salida")
    ex = rr.exit_summary.copy()
    c1, c2 = st.columns(2)
    for col, yrs in ((c1, 5), (c2, 10)):
        with col:
            st.markdown(f"### A {yrs} años")
            show_cols_table(ex[ex["Años"] == yrs].drop(columns="Años").set_index("Escenario"), height=180)

    st.markdown("## 1. Umbral: lo que el precio exige al futuro")
    eps0 = ca.fin.get("eps_diluted", ca.fin.years[-1])
    kv_table({"Precio pagado P": ca.params.price, "Rentabilidad exigida r": ca.params.r, "Horizonte n (años)": f"{ca.params.n}",
              "PER pagado": ca.params.price / eps0 if eps0 and eps0 > 0 else None, "Margen de seguridad exigido": ca.params.mos,
              "Umbral: VF requerido = P × (1 + r)^n": rr.coverage["Umbral: VF requerido = P × (1 + r)^n"]})

    st.markdown("## 2. Distribución de valores futuros en el año n")
    st.caption("Probabilidades de prueba (paso 10: desconfiar y acotar): engordan la cola izquierda sin tocar la estimación principal.")
    cols = st.columns(4)
    for i, scn in enumerate(A.SCENARIOS):
        cols[i].number_input(f"Prob. de prueba · {scn} (%)", 0.0, 100.0, step=5.0, key=_key(T, "tp", scn))
    tsum = sum(rin["test_probs"].values())
    if abs(tsum - 1) > 1e-4:
        st.markdown(f"<span class='pill ko'>Las probabilidades de prueba suman {tsum:.0%}</span>", unsafe_allow_html=True)
    show_rows_table(rr.distribution, kinds={"Exceso (+) / déficit (−) vs umbral": "ps", "Ponderado (prueba)": "ps"})
    fig = go.Figure()
    for scn in A.SCENARIOS:
        g = rr.distribution.at["Ponderado por probabilidad", scn]
        fig.add_bar(x=[scn], y=[g], marker_color=GREEN if g >= 0 else RED, name=scn, showlegend=False,
                    text=[f"{g:,.0f}"], textposition="outside")
    fig.add_hline(y=0, line_color=MUTED)
    st.plotly_chart(fig_layout(fig, "Exceso o déficit ponderado por probabilidad (oportunidad vs riesgo)", 280, unit=f"{cur()} por acción"), width="stretch")

    st.markdown("## 3. Test de cobertura")
    c1, c2 = st.columns([3, 2])
    with c1:
        kv_table(rr.coverage)
    with c2:
        st.markdown("### Prueba de la cola izquierda")
        kv_table(rr.coverage_test)

    st.markdown("## 4. Ventana de horizontes (escenario base)")
    show_rows_table(v.window.loc[["BPA escenario base B(n)", "Umbral P·(1+r)^n", "Múltiplo de salida requerido", "Múltiplo de referencia",
                                  "¿Dentro de la ventana?", "Crecimiento del BPA que exige el precio", "Crecimiento del BPA en el escenario base"]])
    kv_table({k: str(x) for k, x in rr.window_summary.items()})

    st.markdown("## 5. Valor estimado y margen de seguridad")
    kv_table(rr.value)
    st.caption("Precios de prueba: escribe a qué precios quieres ver el test.")
    cols = st.columns(3)
    for i in range(3):
        cols[i].number_input(f"Precio de prueba {i + 1}", min_value=0.0, step=10.0, key=_key(T, "tpx", i))
    pt = rr.price_table.copy()
    show_cols_table(pt, height=38 + 35 * len(pt))

    st.markdown("## 6. Test de exposición: qué significa cada escenario para tu patrimonio")
    c = st.columns(2)
    c[0].number_input("Caída intermedia de la cotización (%)", -99.0, 0.0, step=5.0, key=_key(T, "drop"),
                      help="Ej.: el precio cae temporalmente un 45 % y luego se recupera hacia el escenario base.")
    c[1].number_input("Garantía mínima exigida por el prestamista (%)", 0.0, 100.0, step=5.0, key=_key(T, "ming"),
                      help="Capital propio / valor de la posición por debajo del cual puede reclamar garantías.")
    st.caption("Perfiles de inversor: edita, añade o borra filas. Peso = capital propio invertido / patrimonio (0,10 = 10 %).")
    pdf = pd.DataFrame(st.session_state[_key(T, "perfiles")], columns=["Inversor", "Peso", "Deuda / capital", "Lectura"])
    edited = st.data_editor(pdf, num_rows="dynamic", width="stretch", key=_key(T, "perfiles_editor"),
                            column_config={"Peso": st.column_config.NumberColumn(format="%.2f", step=0.05),
                                           "Deuda / capital": st.column_config.NumberColumn(format="%.2f", step=0.25)})
    st.session_state[_key(T, "perfiles")] = edited.fillna({"Peso": 0.0, "Deuda / capital": 0.0, "Inversor": "", "Lectura": ""}).to_dict("records")
    show_cols_table(rr.exposure.set_index("Inversor"), height=38 + 35 * len(rr.exposure),
                    kinds={**{scn: "pct" for scn in A.SCENARIOS}, "Deuda / capital propio": "x"})
    st.caption("Efecto sobre el patrimonio = peso × (1 + deuda/capital) × (VF / P − 1). Un −100 % o peor significa perder todo el capital invertido. "
               "Supervivencia: Bajo = sin deuda, nadie puede forzar la venta · Alto = el capital propio cae por debajo de la garantía mínima · "
               "Muy alto = la deuda supera la posición.")

    st.markdown("## 7. Preguntas de supervivencia (respóndelas antes de comprar)")
    for i, q in enumerate(R.SURVIVAL_QUESTIONS):
        st.text_area(q, key=_key(T, "surv", i), height=70)
    st.caption(rr.conclusion[-1])


def _tab_filings(ca):
    explica("filings")
    from ui import sec_busqueda
    sec_busqueda.box(ca)
    st.markdown("## Últimas presentaciones")
    try:
        fl = _filings(ca.fin.cik)
    except Exception as e:  # noqa: BLE001
        st.error(f"No he podido leer las presentaciones: {e}")
        return
    st.caption("Últimas presentaciones en EDGAR. El 10-K es el informe anual; el DEF 14A, la junta (retribución de la dirección).")
    df = pd.DataFrame(fl)
    if df.empty:
        st.info("Sin presentaciones recientes.")
        return
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("Documento", display_text="Abrir")})


def _tab_notas(T, ca):
    from ui import bitacora
    bitacora.tab(T, ca)
    with st.expander("Tesis y seguimiento (texto libre)", expanded=False):
        st.text_area("Tesis (modelo de negocio, ventaja competitiva, por qué la entiendo)", key=_key(T, "tesis"), height=220)
        st.text_area("Seguimiento (resultados, cambios en la dirección, guía…)", key=_key(T, "seguimiento"), height=180)
        st.caption("Se guarda con el botón «Guardar análisis».")


def _excel(ca) -> bytes:
    bio = io.BytesIO()
    f = ca.fin
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        f.table(F.PYG_ROWS).to_excel(xw, sheet_name="PyG")
        f.table(F.BALANCE_ROWS).to_excel(xw, sheet_name="Balance")
        f.table(F.CASHFLOW_ROWS).to_excel(xw, sheet_name="Cash Flow")
        ca.eps_df.to_excel(xw, sheet_name="Modelo EPS")
        ca.roic_df.to_excel(xw, sheet_name="ROIC")
        ex = [{"Bloque": b, "Pregunta": t, "Respuesta": (o[ca.answers[q] - 1] if ca.answers.get(q) else (E.NA if ca.answers.get(q) == 0 else "")), "Puntos": ca.answers.get(q)}
              for q, b, t, o in E.QUESTIONS]
        pd.DataFrame(ex).to_excel(xw, sheet_name="Examen", index=False)
        pd.DataFrame(ca.scenarios).to_excel(xw, sheet_name="Supuestos")
        if ca.val:
            ca.val.by_scenario.to_excel(xw, sheet_name="Valor por escenario")
            pd.Series({**ca.val.coverage, **ca.val.value}).to_frame("Valor").to_excel(xw, sheet_name="Cobertura y valor")
            ca.val.window.to_excel(xw, sheet_name="Ventana")
            for scn, df in ca.val.projections.items():
                df.to_excel(xw, sheet_name=f"Proy. {scn}")
            rk = (ca.saved or {}).get("riesgo") or {}
            rr = R.analyze_risk(ca.val, ca.params, rk.get("test_probs"), rk.get("test_prices"), rk.get("drop", R.DEFAULT_DROP),
                                rk.get("min_guarantee", R.DEFAULT_MIN_GUARANTEE), rk.get("profiles"))
            rr.distribution.to_excel(xw, sheet_name="Riesgo - distribución")
            pd.Series({**rr.coverage, **rr.coverage_test, **rr.window_summary, **rr.value}).to_frame("Valor").to_excel(xw, sheet_name="Riesgo - cobertura")
            rr.price_table.to_excel(xw, sheet_name="Riesgo - precios")
            rr.exposure.to_excel(xw, sheet_name="Riesgo - exposición", index=False)
            pd.DataFrame({"Conclusión": rr.conclusion}).to_excel(xw, sheet_name="Riesgo - conclusión", index=False)
    return bio.getvalue()
