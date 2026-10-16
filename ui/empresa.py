from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import analysis as A, exam as E, financials as F, pipeline, plantilla, riesgo as R, sec, storage
from ui.ayuda import explica
from ui.common import (AMBER, BLUE, GREEN, MUTED, RED, fig_layout, fmt_cell, kv_table, mult, num, pct, show_cols_table,
                       show_rows_table)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _universe_options():
    uni = sec.universe()
    return [f"{u['ticker']} · {u['name']}" for u in uni]


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
            if v is not None:
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


# ------------------------------------------------------------------ página
def page():
    st.markdown("<span class='subtle'>FICHA DE EMPRESA</span>", unsafe_allow_html=True)
    opts = _universe_options()
    default = st.session_state.get("ticker", "ADBE")
    idx = next((i for i, o in enumerate(opts) if o.split(" · ")[0] == default), 0)
    c1, c2 = st.columns([4, 1])
    sel = c1.selectbox("Empresa", opts, index=idx, label_visibility="collapsed", placeholder="Busca ticker o nombre…")
    n_years = c2.selectbox("Años", [10, 12, 15], index=0, label_visibility="collapsed", format_func=lambda x: f"{x} años")
    T = sel.split(" · ")[0]
    st.session_state["ticker"] = T

    with st.spinner(f"Descargando {T} de la SEC…"):
        try:
            meta, fin, hist = _load(T, n_years)
        except Exception as e:  # noqa: BLE001
            st.error(f"No he podido cargar {T}: {e}")
            return
    if not fin.years:
        st.error("La SEC no tiene estados anuales en XBRL para esta empresa (p. ej. emisores extranjeros con IFRS sin etiquetar, SPACs, fondos).")
        return

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
    _save_bar(T, work, ca)

    tabs = st.tabs(["Resumen", "Histórico", "Examen", "Estados financieros", "Modelo EPS", "ROIC", "Escenarios y valoración", "Riesgo",
                    "Presentaciones SEC", "Notas"])
    with tabs[0]:
        _tab_resumen(ca)
    with tabs[1]:
        _tab_historico(T, ca)
    with tabs[2]:
        _tab_examen(T, ca)
    with tabs[3]:
        _tab_estados(ca)
    with tabs[4]:
        _tab_eps(ca)
    with tabs[5]:
        _tab_roic(T, ca)
    with tabs[6]:
        _tab_escenarios(T, ca)
    with tabs[7]:
        _tab_riesgo(T, ca)
    with tabs[8]:
        _tab_filings(ca)
    with tabs[9]:
        _tab_notas(T, ca)


def _header(ca: pipeline.CompanyAnalysis):
    f = ca.fin
    L = f.years[-1]
    eps = f.get("eps_diluted", L)
    P = ca.params.price
    shares = f.get("shares_outstanding", L) or f.get("shares_diluted", L)
    mcap = P * shares if (P and shares) else None
    st.markdown(f"<h1><span class='tick'>{f.ticker}</span>{f.name}</h1>"
                f"<span class='pill'>{ca.meta.get('exchange')}</span><span class='pill'>CIK {f.cik}</span>"
                f"<span class='pill'>Último ejercicio {L} · cierre {f.period_end.get(L, '')}</span>"
                f"<span class='pill am'>Fase: {ca.phase}</span>", unsafe_allow_html=True)
    v = ca.val
    cols = st.columns(8)
    cols[0].metric("Precio", num(P, 2) if P else "—", ca.params.price_date or ("manual" if ca.saved.get("precio_manual") else ""))
    cols[1].metric("PER", mult((P / eps) if (P and eps and eps > 0) else None))
    cols[2].metric("Capitalización", f"{num(mcap / 1000, 1)} B" if mcap else "—")
    cols[3].metric(f"Ventas {L}", f"{num((f.get('revenue', L) or 0) / 1000, 2)} B")
    cols[4].metric("Nota (examen)", f"{ca.score['final']:.2f}" if ca.score["cual_respondidas"] else f"{ca.score['financiera']:.2f}*",
                   f"{ca.score['respondidas']}/{ca.score['total']} resp." if ca.score["cual_respondidas"] else "*solo financiera")
    if v and v.value:
        cols[5].metric("Valor estimado", num(v.value["Valor estimado hoy = E[VF] / (1+r)^n"], 2))
        cols[6].metric("Margen seguridad", pct(v.value["Margen de seguridad al precio actual"]))
        cols[7].metric("Veredicto", v.coverage.get("Veredicto", "—"), f"rent. {pct(v.value['Rentabilidad anual implícita en la media'])}")
    for w in f.warnings + ((v.warnings if v else [])):
        st.caption(f"⚠ {w}")


def _save_bar(T, work, ca):
    c1, c2, c4, c3 = st.columns([1, 1, 1, 3])
    if c4.button("↺ Volver a lo guardado", width="stretch", help="Descarta los cambios sin guardar de esta empresa."):
        _reset_widgets(T)
        st.session_state.pop(f"saved_{T}", None)
        st.rerun()
    if c1.button("💾 Guardar análisis", type="primary", width="stretch"):
        data = dict(work)
        data["resumen"] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in pipeline.summary_row(ca).items()}
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
    c1, c2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=ys, y=f.series("revenue"), name="Ventas (M)", marker_color=BLUE, opacity=.85)
    fig.add_bar(x=ys, y=f.series("net_income"), name="Beneficio neto (M)", marker_color=AMBER)
    fig.add_bar(x=ys, y=f.series("fcf"), name="Flujo de caja libre (M)", marker_color=GREEN, opacity=.8)
    c1.plotly_chart(fig_layout(fig, "Ventas, beneficio y caja libre"), width="stretch")
    fig = go.Figure()
    fig.add_scatter(x=ys, y=f.series("eps_diluted"), name="BPA diluido", mode="lines+markers", line=dict(color=AMBER, width=2))
    eps_df = ca.eps_df
    if eps_df["Precio medio"].notna().any():
        fig.add_scatter(x=ys, y=list(eps_df["PER"]), name="PER (eje dcho.)", yaxis="y2", mode="lines+markers", line=dict(color=MUTED, dash="dot"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
    c2.plotly_chart(fig_layout(fig, "BPA y PER histórico"), width="stretch")
    c3, c4 = st.columns(2)
    fig = go.Figure()
    for k, name, col in [("gm_series", "Margen bruto", BLUE), ("om_series", "Margen operativo", AMBER)]:
        s = ca.stats[k]
        fig.add_scatter(x=[str(y) for y in s], y=list(s.values()), name=name, mode="lines+markers", line=dict(color=col))
    nm = [(n / r) if (n is not None and r) else None for n, r in zip(f.series("net_income"), f.series("revenue"))]
    fig.add_scatter(x=ys, y=nm, name="Margen neto", mode="lines+markers", line=dict(color=GREEN))
    fig.update_yaxes(tickformat=".0%")
    c3.plotly_chart(fig_layout(fig, "Márgenes"), width="stretch")
    fig = go.Figure()
    r = ca.roic_df
    fig.add_scatter(x=ys, y=list(r.loc["ROIC"]), name="ROIC", mode="lines+markers", line=dict(color=AMBER))
    fig.add_scatter(x=ys, y=list(r.loc["ROIC ajustado (I+D capitalizado)"]), name="ROIC ajustado I+D", mode="lines+markers", line=dict(color=BLUE))
    fig.add_scatter(x=ys, y=list(eps_df["ROE"]), name="ROE", mode="lines+markers", line=dict(color=MUTED, dash="dot"))
    fig.update_yaxes(tickformat=".0%")
    c4.plotly_chart(fig_layout(fig, "Rentabilidad del capital"), width="stretch")

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
    f = ca.fin
    names = [m[0] for m in HIST_METRICS]
    c1, c2 = st.columns([2, 5])
    sel = c1.radio("Métrica", names, key=_key(T, "hist_sel"), label_visibility="collapsed")
    label, key, kind = next(m for m in HIST_METRICS if m[0] == sel)
    vals = _hist_series(ca, key)
    ys = [str(y) for y in f.years]
    with c2:
        st.markdown(f"### {f.name.title()} · {label} {f.years[0]}-{f.years[-1]} | {f.ticker}")
        fig = go.Figure()
        fig.add_bar(x=ys, y=vals, marker_color=BLUE, text=[fmt_cell(v, kind) for v in vals], textposition="outside",
                    textfont=dict(size=11), hovertemplate="%{x}: %{text}<extra></extra>")
        if kind == "pct":
            fig.update_yaxes(tickformat=".0%")
        fig_layout(fig, "", 380)
        fig.update_layout(bargap=0.25)
        st.plotly_chart(fig, width="stretch")
        rows = []
        prev = None
        for y, v in zip(f.years, vals):
            chg = (v / prev - 1) if (kind != "pct" and v is not None and prev not in (None, 0) and prev > 0) else None
            rows.append({"Año fiscal": str(y), "Cierre": f.period_end.get(y, ""), label: fmt_cell(v, kind),
                         "Variación anual": pct(chg) if chg is not None else "—"})
            prev = v
        st.dataframe(pd.DataFrame(rows[::-1]).set_index("Año fiscal"), width="stretch", height=38 + 35 * len(rows))
        unit = f"millones de {f.currency}" if kind == "m" else ("por acción" if kind == "ps" else "")
        st.caption(f"{label}{' en ' + unit if unit else ''}. Fuente: 10-K en SEC EDGAR.")


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
    for title, rows in [("Cuenta de resultados (PyG)", F.PYG_ROWS), ("Balance", F.BALANCE_ROWS), ("Cash Flow", F.CASHFLOW_ROWS)]:
        st.markdown(f"## {title}")
        df = f.table(rows)
        show_rows_table(df, kinds=m_kinds)
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
        show_rows_table(base.loc[keep], kinds={"Ventas": "m", "Beneficio neto": "m", "Acciones diluidas (M)": "m"})
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
                                       "Amortización del I+D capitalizado": "m", "Ajuste al EBIT": "m"})


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
    st.caption("Cada casilla vacía usa la propuesta según la fase (la ves en gris). Escribe encima para fijar tu supuesto; bórrala para volver a la propuesta. "
               "Porcentajes en %. Si dejas el PER vacío se recalcula con el crecimiento del año 10.")
    head = st.columns([2.2, 1, 1, 1, 1])
    head[0].markdown("<span class='subtle'>Supuesto</span>", unsafe_allow_html=True)
    for i, scn in enumerate(A.SCENARIOS):
        head[i + 1].markdown(f"**{scn}**")
    for fld, lbl, kind in A.SCENARIO_FIELDS:
        row = st.columns([2.2, 1, 1, 1, 1])
        row[0].markdown(f"<div style='padding-top:.45rem'>{lbl}</div>", unsafe_allow_html=True)
        for i, scn in enumerate(A.SCENARIOS):
            prop = ca.proposed[scn][fld] if fld != "per_exit" else A.exit_per(ca.scenarios[scn]["g10"], ca.params.r, ca.stats.get("roe5"))
            ph = f"{prop * 100:.2f}" if kind == "pct" else f"{prop:.2f}"
            row[i + 1].number_input(lbl, step=0.5 if kind == "pct" else 0.5, format="%.2f", key=_key(T, "sc", scn, fld),
                                    placeholder=ph, label_visibility="collapsed")
    psum = sum(ca.scenarios[s]["prob"] for s in A.SCENARIOS)
    st.markdown(f"<span class='pill {'ok' if abs(psum - 1) < 1e-4 else 'ko'}'>Suma de probabilidades: {psum:.0%}</span>", unsafe_allow_html=True)

    v = ca.val
    if not v:
        st.info("Necesito un precio y un BPA para valorar.")
        return
    st.markdown("## 4. Valor futuro por escenario")
    explica("esc_4")
    show_rows_table(v.by_scenario)
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
    st.plotly_chart(fig_layout(fig, f"Valor futuro en el año {ca.params.n} frente al umbral", 340), width="stretch")

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
                                       "Variación de deuda": "m", "Acciones diluidas (M)": "m"})


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
    st.plotly_chart(fig_layout(fig, "Exceso o déficit ponderado por probabilidad (oportunidad vs riesgo)", 280), width="stretch")

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
