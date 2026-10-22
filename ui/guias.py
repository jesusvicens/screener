"""Pestaña «Guías y resultados»: qué prometió la dirección cada trimestre, qué cumplió y cómo fue cambiando la guía anual."""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from terminal import onedrive as OD
from terminal import sec, storage, trimestres
from ui.common import BLUE, cur, GREEN, MUTED, RED, fmt_cell, show_cols_table

AMBER = "#e07b39"
METRICAS = [("Ingresos", "m"), ("BPA non-GAAP", "ps"), ("BPA GAAP", "ps"), ("Ingresos BP&C", "m"), ("Ingresos C&MP", "m"),
            ("Ingresos Digital Media", "m"), ("Ingresos Digital Experience", "m"), ("Nuevo ARR Digital Media", "m"),
            ("Margen operativo non-GAAP", "pct")]


def _fmt(v, kind):
    """Cifra con su unidad: millones de $ («M$»), $ por acción («$») o millones de acciones («M acc.»)."""
    if v is None:
        return "—"
    return fmt_cell(v, "m" if kind == "sh" else kind) + {"m": f" M{cur()}", "ps": f" {cur()}", "sh": " M acc."}.get(kind, "")


def _rng(r, kind):
    if not r:
        return "—"
    return _fmt(r[0], kind) if r[0] == r[1] else f"{_fmt(r[0], kind)} – {_fmt(r[1], kind)}"


def _md(t: str) -> str:
    """Evita que Streamlit interprete los «$» como fórmulas."""
    return (t or "").replace("$", "\\$")


def _veredicto(real, r):
    if real is None or not r:
        return None, None
    mid = (r[0] + r[1]) / 2
    dif = real / mid - 1 if mid else None
    if r[0] == r[1]:  # guía aproximada («~44 %»): en línea si se queda a menos de un 1 % (o medio punto)
        tol = 0.005 if abs(mid) < 1 else abs(mid) * 0.01
        if abs(real - mid) <= tol:
            return "Dentro", dif
    if real > r[1]:
        return "Por encima", dif
    if real >= r[0]:
        return "Dentro", dif
    return "Por debajo", dif


# ------------------------------------------------------------------ pestaña
def tab(T: str, ca):
    data = (storage.load(T) or {}).get("guias") if storage else None
    qs = (data or {}).get("trimestres") or []
    if not qs:
        _sin_guias(T, ca)
        return
    st.caption(f"{data.get('fuente', '')} {data.get('unidades', '')} Actualizado: {data.get('actualizado', '')}.")
    eu = not int(ca.meta.get("cik") or 0)
    names = ["Guía vs. resultado", "Evolución de la guía anual", "Trimestre a trimestre",
             "Resultados publicados" if eu else "Resultados trimestrales (SEC)"]
    extra = []
    if data.get("kpis"):
        extra.append(("KPIs y segmentos: dicho vs. hecho", lambda: _kpis(ca, data)))
    tabs = st.tabs([n for n, _ in extra] + names, key=f"guias_tabs_{T}")
    for (n, fn), tb in zip(extra, tabs):
        with tb:
            fn()
    tabs = tabs[len(extra):]
    t1, t2, t3, t4 = tabs
    with t1:
        _guia_vs_real(qs, data)
    with t2:
        _guia_anual(qs)
    with t3:
        _trimestre(T, ca, qs)
    with t4:
        _xbrl(ca)


KPI_COLS = [("uglob", "Unidades globales"), ("uaseg", "Unid. aseguradoras EE. UU."), ("uaseg_xc", "Aseg. EE. UU. sin catástrofes"),
            ("unoaseg", "Unid. no aseguradoras EE. UU."), ("uint", "Unid. internacionales"), ("bluecar", "BlueCar"),
            ("dealer", "Concesionarios"), ("ucomp", "Unid. compradas EE. UU."), ("aspg", "ASP global"), ("aspa", "ASP aseguradoras EE. UU."),
            ("aspi", "ASP internacional"), ("inv", "Inventario")]
PAL = ["#2f6db5", "#e07b24", "#2e8b57", "#7c5cbf", "#3a9fb5", "#6b7280"]


def _kpi_chart(ks, keys, title, unit="% interanual"):
    fig = go.Figure()
    x = [k["q"].replace("FY20", "FY") for k in ks]
    for i, (key, lab) in enumerate(keys):
        y = [k.get(key) for k in ks]
        if any(v is not None for v in y):
            fig.add_scatter(x=x, y=y, name=lab, mode="lines+markers", connectgaps=True, line=dict(color=PAL[i % len(PAL)], width=2),
                            marker=dict(size=7), hovertemplate="%{y:+.1f} %<extra>" + lab + "</extra>")
    fig.add_hline(y=0, line_color="#c9ced6", line_width=1)
    from ui.common import fig_layout
    fig_layout(fig, title, h=360, unit=unit)
    fig.update_yaxes(ticksuffix=" %")
    fig.update_xaxes(tickangle=-45, tickfont=dict(size=10))
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=11)), margin=dict(t=70))
    return fig


def _kpis(ca, data):
    """Indicadores que la dirección cuenta en cada call + segmentos de los 10-Q, y su relación con la estrategia."""
    ks = data["kpis"]
    st.caption(data.get("kpis_fuente", ""))
    c = st.columns(2)
    c[0].plotly_chart(_kpi_chart(ks, [("uglob", "Globales"), ("uaseg", "Aseguradoras EE. UU."), ("uaseg_xc", "Aseg. EE. UU. sin catástrofes"),
                                      ("uint", "Internacionales")], "Unidades vendidas"), width="stretch", key="kpi_u")
    c[1].plotly_chart(_kpi_chart(ks, [("aspg", "Global"), ("aspa", "Aseguradoras EE. UU."), ("aspi", "Internacional")],
                                 "Precio medio de venta (ASP)"), width="stretch", key="kpi_asp")
    c = st.columns(2)
    c[0].plotly_chart(_kpi_chart(ks, [("bluecar", "BlueCar"), ("dealer", "Concesionarios"), ("unoaseg", "No aseguradoras EE. UU."),
                                      ("ucomp", "Coches comprados EE. UU.")], "No aseguradoras y coches comprados"), width="stretch", key="kpi_na")
    tl = [k for k in ks if k.get("tlf") is not None]
    if tl:
        fig = go.Figure(go.Scatter(x=[k["tlf_per"] for k in tl], y=[k["tlf"] for k in tl], mode="lines+markers+text",
                                   text=[f"{k['tlf']:.1f}".replace(".", ",") for k in tl], textposition="top center",
                                   line=dict(color="#2f6db5", width=2), marker=dict(size=8),
                                   hovertemplate="%{x}: %{y:.1f} %<extra>Pérdida total</extra>"))
        fig.add_hline(y=21.7, line_dash="dash", line_color="#6b7280", line_width=1, annotation_text="máximo pre-COVID 21,7 %",
                      annotation_position="bottom right")
        from ui.common import fig_layout
        fig_layout(fig, "Frecuencia de pérdida total en EE. UU. (CCC)", h=330, unit="% de los siniestros, por trimestre natural")
        fig.update_yaxes(ticksuffix=" %")
        fig.update_layout(showlegend=False)
        c[1].plotly_chart(fig, width="stretch", key="kpi_tlf")
    # segmentos trimestrales (XBRL)
    try:
        from terminal import segmentos as SG
        sq = SG.quarterly(int(ca.meta["cik"])) if int(ca.meta.get("cik") or 0) else pd.DataFrame()
        d = sq[sq["Tipo"] == "Segmento"].pivot_table(index="Fin", columns=["Dato", "Miembro"], values="Valor") if not sq.empty else None
    except Exception:  # noqa: BLE001
        d = None
    if d is not None and not d.empty and "Ventas" in d:
        st.markdown("#### Segmentos por trimestre (10-Q / 10-K)")
        v = d["Ventas"]
        o = d["Resultado operativo"] if "Resultado operativo" in d else None
        x = [pd.Timestamp(i).strftime("%b %y") for i in v.index]
        c = st.columns(2)
        fig = go.Figure()
        for i, m in enumerate(v.columns):
            fig.add_scatter(x=x, y=list(v[m].pct_change(4) * 100), name=m, mode="lines+markers", line=dict(color=PAL[i], width=2),
                            hovertemplate="%{y:+.1f} %<extra>" + m + "</extra>")
        fig.add_hline(y=0, line_color="#c9ced6", line_width=1)
        from ui.common import fig_layout
        fig_layout(fig, "Crecimiento de las ventas por segmento", h=320, unit="% interanual")
        fig.update_yaxes(ticksuffix=" %")
        c[0].plotly_chart(fig, width="stretch", key="seg_g")
        if o is not None:
            fig = go.Figure()
            for i, m in enumerate(v.columns):
                if m in o:
                    fig.add_scatter(x=x, y=list(o[m] / v[m] * 100), name=m, mode="lines+markers", line=dict(color=PAL[i], width=2),
                                    hovertemplate="%{y:.1f} %<extra>" + m + "</extra>")
            fig_layout(fig, "Margen operativo por segmento", h=320, unit="% de las ventas del segmento")
            fig.update_yaxes(ticksuffix=" %")
            c[1].plotly_chart(fig, width="stretch", key="seg_m")
        tb = v.copy()
        tb.columns = [f"Ventas {m} (M$)" for m in v.columns]
        if o is not None:
            for m in v.columns:
                if m in o:
                    tb[f"Margen op. {m}"] = o[m] / v[m]
        tb.index = x
        show_cols_table(tb.iloc[::-1], height=min(38 + 35 * len(tb), 420),
                        kinds={c_: ("pct" if c_.startswith("Margen") else "m") for c_ in tb.columns})
    if data.get("kpis_lectura"):
        st.markdown("#### Lo que decían y lo que muestran los datos")
        st.markdown(_md(data["kpis_lectura"]))
    st.markdown("#### Tabla de indicadores por trimestre (lo dicho en cada call)")
    rows = []
    for k in ks:
        r = {"Trimestre": k["q"], "Call": k.get("fecha")}
        for key, lab in KPI_COLS:
            r[lab] = (k.get(key) / 100) if k.get(key) is not None else None
        r["Pérdida total"] = (f"{k['tlf']:.1f} % ({k['tlf_per']})".replace(".", ",") if k.get("tlf") is not None else (k.get("tlf_per") or ""))
        r["Catástrofes y notas"] = k.get("cat") or ""
        rows.append(r)
    t = pd.DataFrame(rows[::-1]).set_index("Trimestre")
    show_cols_table(t, height=min(38 + 35 * len(t), 700), kinds={lab: "pct" for _k, lab in KPI_COLS})
    st.caption("Variaciones interanuales tal como las dijo la dirección (a veces «casi», «más de»); vacío = no lo dijeron en esa call. "
               "Los nombres de cada indicador cambian algo con los años (p. ej. qué incluye «no aseguradoras»).")


def estrategia_tab(T: str):
    """Pestaña «Estrategia año a año» (grupo Negocio)."""
    data = (storage.load(T) or {}).get("guias") or {}
    if not data.get("estrategia_anual"):
        st.info("Aún no está la estrategia año a año de esta empresa. Pídemela en el chat: la saco de las presentaciones de "
                "resultados y de las transcripciones de las calls.")
        return
    _estrategia(data)


def _estrategia(data):
    """Qué dijo la dirección cada año en sus presentaciones de resultados y cuál era su estrategia."""
    if data.get("estrategia_resumen"):
        st.markdown("#### Cómo ha evolucionado la estrategia")
        st.markdown(_md(data["estrategia_resumen"]))
    st.caption(data.get("estrategia_fuente", ""))
    for y in data["estrategia_anual"][::-1]:
        with st.expander(f"**{y['año']}** · {y.get('titulo', '')}", expanded=y is data["estrategia_anual"][-1]):
            if y.get("contexto"):
                st.markdown(f"<span class='subtle'>{_md(y['contexto'])}</span>", unsafe_allow_html=True)
            c = st.columns(2)
            with c[0]:
                st.markdown("**Estrategia que presentan**")
                st.markdown("\n".join(f"- {_md(x)}" for x in y.get("estrategia", [])))
            with c[1]:
                st.markdown("**Qué dicen (mensajes clave)**")
                st.markdown("\n".join(f"- {_md(x)}" for x in y.get("mensajes", [])))
            if y.get("cumplimiento"):
                st.markdown(f"**Lo que cumplieron:** {_md(y['cumplimiento'])}")
            if y.get("tono"):
                st.markdown(f"**Tono:** {_md(y['tono'])}")
            if y.get("llamadas"):
                st.markdown("**Transcripciones:** " + " · ".join(f"[{l['trimestre']}]({l['url']})" for l in y["llamadas"]))


def _sin_guias(T, ca):
    st.info("Aún no hay guías guardadas para esta empresa. Pídemelo en el chat: leo sus notas de resultados en la SEC "
            "(y las transcripciones de tu OneDrive) y guardo aquí la guía de cada trimestre, el resultado y el resumen de la call. "
            "Mientras, abajo tienes sus resultados trimestrales reales sacados de la SEC.")
    _xbrl(ca)


def _kind(m: str) -> str:
    """Tipo de dato de una métrica que no está en la lista fija (para empresas con otros indicadores)."""
    l = m.lower()
    if l.startswith(("crec", "margen")) or "%" in l or "frecuencia" in l or "tasa" in l:
        return "pct"
    if "bpa" in l or "por acción" in l:
        return "ps"
    if "acciones" in l or "unidades" in l:
        return "sh"
    return "m"


def _sin_guia_numerica(qs, data):
    st.info(data.get("nota_guia") or "Esta empresa no da guía numérica de resultados: no hay promesas que comparar con la realidad. "
            "En «Trimestre a trimestre» tienes el resumen de cada presentación y en «Resultados trimestrales» las cifras de la SEC.")
    rows = []
    for q in qs:
        r = q.get("real") or {}
        rows.append({"Trimestre": q["trimestre"], "Publicado": q.get("publicado"), "Ingresos": _fmt(r.get("Ingresos"), "m"),
                     "Crec. interanual": fmt_cell(r.get("Crec. ingresos"), "pct") if r.get("Crec. ingresos") is not None else "—",
                     "BPA": _fmt(r.get("BPA GAAP") if r.get("BPA GAAP") is not None else r.get("BPA"), "ps"),
                     "Tono": q.get("tono") or ""})
    st.dataframe(pd.DataFrame(rows[::-1]).set_index("Trimestre"), width="stretch", height=min(38 + 35 * len(rows), 600))


def _guia_vs_real(qs, data=None):
    disp = [m for m, _k in METRICAS if any((q.get("guia_previa") or {}).get(m) for q in qs)]
    if not disp:
        _sin_guia_numerica(qs, data or {})
        return
    c = st.columns([2, 3])
    met = c[0].selectbox("Métrica", disp, index=0, key="gvr_met")
    kind = dict(METRICAS)[met]
    rows, x, lo, hi, real = [], [], [], [], []
    for q in qs:
        g = (q.get("guia_previa") or {}).get(met)
        r = q["real"].get(met)
        if g is None:
            continue
        v, dif = _veredicto(r, g)
        rows.append({"Trimestre": q["trimestre"], "Publicado": q["publicado"], "Guía (dada el trimestre anterior)": _rng(g, kind),
                     "Real": _fmt(r, kind), "vs. punto medio": fmt_cell(dif, "pct") if dif is not None else "—",
                     "Resultado": {"Por encima": "🟢 Por encima", "Dentro": "🟡 Dentro", "Por debajo": "🔴 Por debajo"}.get(v, "—")})
        x.append(q["trimestre"]); lo.append(g[0]); hi.append(g[1]); real.append(r)
    if not rows:
        st.caption("Sin datos para esta métrica.")
        return
    n = len(rows)
    enc = sum(1 for r in rows if "encima" in r["Resultado"])
    den = sum(1 for r in rows if "Dentro" in r["Resultado"])
    deb = n - enc - den
    m = st.columns(4)
    m[0].metric("Trimestres con guía", n)
    m[1].metric("Por encima de la guía", f"{enc} ({enc / n:.0%})")
    m[2].metric("Dentro", den)
    m[3].metric("Por debajo", deb)
    fig = go.Figure()
    cols = []
    for r, l, h in zip(real, lo, hi):
        v, _d = _veredicto(r, [l, h])
        cols.append({"Por encima": GREEN, "Dentro": AMBER}.get(v, RED))
    fig.add_trace(go.Bar(x=x, y=real, name="Real", marker_color=cols, opacity=.8,
                         text=[_fmt(r, kind) for r in real], textposition="outside", textfont=dict(size=10)))
    mids = [(l + h) / 2 for l, h in zip(lo, hi)]
    fig.add_trace(go.Scatter(x=x, y=mids, mode="markers", name="Guía (rango)", marker=dict(color="#1b2a41", size=7, symbol="line-ew-open"),
                             error_y=dict(type="data", symmetric=False, array=[h - m for h, m in zip(hi, mids)],
                                          arrayminus=[m - l for l, m in zip(lo, mids)], color="#1b2a41", thickness=2, width=10),
                             hovertemplate="%{x}: guía %{y}<extra></extra>"))
    lo_all = min(v for v in lo + [r for r in real if r is not None])
    hi_all = max(v for v in hi + [r for r in real if r is not None])
    pad = (hi_all - lo_all) * 0.15 or abs(hi_all) * 0.05
    fig.update_layout(template="terminal", height=380, margin=dict(l=10, r=10, t=10, b=10), barmode="overlay",
                      legend=dict(orientation="h", y=1.08), yaxis=dict(range=[lo_all - pad * 3, hi_all + pad],
                                                                       tickformat=".0%" if kind == "pct" else None))
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    st.caption("La raya negra es el rango que dio la dirección un trimestre antes; la barra es el resultado (verde: por encima, "
               "ámbar: dentro, rojo: por debajo). El eje no empieza en cero para que se vea la diferencia.")
    df = pd.DataFrame(rows[::-1]).set_index("Trimestre")
    st.dataframe(df, width="stretch", height=38 + 35 * len(df))


def _guia_anual(qs):
    fys = sorted({(q.get("guia_anual") or {}).get("periodo") for q in qs if q.get("guia_anual")})
    if not fys:
        st.caption("Sin guías anuales.")
        return
    c = st.columns([2, 2, 3])
    fy = c[0].selectbox("Año fiscal", fys[::-1], key="ga_fy")
    disp = [m for m, _k in METRICAS if any(((q.get("guia_anual") or {}).get("periodo") == fy and (q.get("guia_anual") or {}).get(m)) for q in qs)]
    met = c[1].selectbox("Métrica", disp, key="ga_met")
    kind = dict(METRICAS)[met]
    rows, last = [], None
    for q in qs:
        ga = q.get("guia_anual") or {}
        if ga.get("periodo") == fy and ga.get(met):
            last = ga[met]
            estado = "Primera guía" if not rows else ("Sube" if (last[0] + last[1]) / 2 > rows[-1]["_mid"] + 1e-9 else
                                                       ("Baja" if (last[0] + last[1]) / 2 < rows[-1]["_mid"] - 1e-9 else "Se mantiene"))
            rows.append({"Fecha": q["publicado"], "Con los resultados de": q["trimestre"], "Guía": _rng(last, kind), "_mid": sum(last) / 2,
                         "Cambio": estado})
        elif rows and q["publicado"] > rows[-1]["Fecha"] and int(q["trimestre"][-4:]) == int(fy[-4:]) and not ga.get("periodo"):
            rows.append({"Fecha": q["publicado"], "Con los resultados de": q["trimestre"], "Guía": _rng(last, kind), "_mid": sum(last) / 2,
                         "Cambio": "Reafirmada"})
    # resultado final del año, si ya cerró
    fin = None
    if met in ("Ingresos", "BPA GAAP", "BPA non-GAAP"):
        q4 = [q for q in qs if q["trimestre"] == f"Q4 {fy}"]
        yq = [q for q in qs if q["trimestre"].endswith(fy)]
        if q4 and len(yq) == 4:
            fin = sum(q["real"].get(met) or 0 for q in yq)
    if not rows:
        st.caption("Sin datos.")
        return
    fig = go.Figure()
    xs = [f"{r['Fecha']}<br>{r['Con los resultados de']}" for r in rows]
    fig.add_trace(go.Scatter(x=xs, y=[r["_mid"] for r in rows], mode="lines+markers+text", line=dict(color=BLUE, width=2.5),
                             text=[_fmt(r["_mid"], kind) for r in rows], textposition="top center", name="Punto medio de la guía"))
    if fin:
        fig.add_hline(y=fin, line_dash="dot", line_color=GREEN, annotation_text=f"Resultado final {_fmt(fin, kind)}",
                      annotation_position="bottom right")
    fig.update_layout(template="terminal", height=360, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_mid"} for r in rows]).set_index("Fecha")
    st.dataframe(df, width="stretch", height=38 + 35 * len(df))
    if fin:
        first = rows[0]["_mid"]
        st.markdown(f"**Resultado final de {fy}: {_fmt(fin, kind)}**, un {fmt_cell(fin / first - 1, 'pct')} sobre el punto medio de la "
                    f"primera guía ({_fmt(first, kind)}).")
    st.caption("Muestra cómo la dirección fue cambiando la guía del año con cada presentación de resultados. Subidas seguidas y un "
               "resultado final por encima de la primera guía indican una dirección que guía con prudencia.")


def _find_any_transcript(items):
    """Un documento con varias transcripciones (p. ej. «earnings calls 2020-2026.docx»)."""
    found = []

    def walk(its):
        for it in its:
            if it.get("folder"):
                walk(it.get("children", []))
            else:
                nm = it["name"].lower()
                if "transcript" in nm or "earnings call" in nm or "conference call" in nm:
                    found.append(it)
    walk(items)
    return sorted(found, key=lambda x: x.get("modified") or "", reverse=True)[0] if found else None


def _find_transcript(items, trimestre: str):
    m = re.match(r"Q(\d) FY(\d{4})", trimestre)
    if not m:
        return None
    n, y = m.group(1), m.group(2)
    keys = {f"q{n}fy{y}", f"q{n}fy{y[2:]}"}
    found = []

    def walk(its):
        for it in its:
            if it.get("folder"):
                walk(it.get("children", []))
            else:
                nm = re.sub(r"[^a-z0-9]", "", it["name"].lower())
                if "transcript" in nm and any(k in nm for k in keys):
                    found.append(it)
    walk(items)
    return found[0] if found else None


def _trimestre(T, ca, qs):
    opts = [q["trimestre"] for q in qs][::-1]
    sel = st.selectbox("Trimestre", opts, key=f"gq_sel_{T}")
    q = next(x for x in qs if x["trimestre"] == sel)
    st.markdown(f"### {sel} · resultados publicados el {q['publicado']} (cierre {q['cierre']})")
    if q.get("titular"):
        st.markdown(f"**{_md(q['titular'])}**")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### Resumen de la presentación de resultados")
        st.markdown(_md(q.get("resumen")) or "—")
        if q.get("tono"):
            st.markdown(f"**Tono:** {_md(q['tono'])}")
        if q.get("fuente_resumen"):
            st.caption(f"Fuente del resumen: {q['fuente_resumen']}")
        if q.get("citas"):
            with st.expander("Citas de la dirección (nota de prensa)"):
                for ct in q["citas"]:
                    st.markdown(f"> {_md(ct)}")
    with c2:
        st.markdown("#### Real frente a la guía" if any(q.get("guia_previa") or {} for q in qs) else "#### Cifras del trimestre")
        g = q.get("guia_previa") or {}
        rows = []
        for m, k in METRICAS:
            r = q["real"].get(m)
            if r is None and m not in g:
                continue
            v, dif = _veredicto(r, g.get(m))
            rows.append({"Métrica": m, "Guía": _rng(g.get(m), k), "Real": _fmt(r, k),
                         "": {"Por encima": "🟢", "Dentro": "🟡", "Por debajo": "🔴"}.get(v, "")})
        shown = {m for m, _k in METRICAS}
        for m, v in q["real"].items():  # el resto de indicadores que publica la empresa
            if m in shown or v is None:
                continue
            k = "sh" if m == "Acciones recompradas (M)" else _kind(m)
            rows.append({"Métrica": m, "Guía": "", "Real": _fmt(v, k), "": ""})
        st.dataframe(pd.DataFrame(rows).set_index("Métrica"), width="stretch", height=38 + 35 * len(rows))
    st.markdown("#### Guía que dio en esta presentación")
    gc = st.columns(2)
    for col, key, tit in [(gc[0], "guia_siguiente", "Para el trimestre siguiente"), (gc[1], "guia_anual", "Para el año fiscal")]:
        gg = q.get(key)
        with col:
            if gg:
                st.markdown(f"**{tit} ({gg.get('periodo')})**")
                rr = [{"Métrica": m, "Guía": _rng(gg[m], k)} for m, k in METRICAS if gg.get(m)]
                st.dataframe(pd.DataFrame(rr).set_index("Métrica"), width="stretch", height=38 + 35 * len(rr))
            else:
                st.markdown(f"**{tit}:** reafirmada (sin cambios) o no publicada.")
    st.markdown("#### Transcripción y documentos")
    links = []
    if q.get("nota_prensa"):
        links.append(f"[Nota de prensa en la SEC]({q['nota_prensa']})")
    if q.get("transcripcion_url"):
        links.append(f"[Transcripción completa de la call]({q['transcripcion_url']})")
    st.markdown(" · ".join(links) if links else "")
    _transcripcion(T, ca, sel)


def _transcripcion(T, ca, sel):
    if not (OD.configured() and OD.connected()):
        st.caption("Conecta OneDrive (Seguimiento → Documentos) para ver aquí las transcripciones que guardas en la carpeta de la empresa.")
        return
    folder = OD.settings()["carpetas"].get(T)
    if not folder:
        st.caption("Guarda la carpeta de OneDrive de esta empresa (Seguimiento → Documentos) para buscar la transcripción.")
        return
    try:
        from ui.cualitativo import _tree_cached
        it = _find_transcript(_tree_cached(folder), sel)
    except OD.OneDriveError as e:
        st.caption(str(e))
        return
    if not it:
        it = _find_any_transcript(_tree_cached(folder))
        if it:
            st.caption(f"No hay un fichero solo de {sel}; este documento de tu carpeta reúne varias calls:")
    if not it:
        st.caption(f"No encuentro la transcripción de {sel} en tu carpeta de OneDrive. Si la guardas con un nombre que incluya, por "
                   f"ejemplo, «{sel.replace(' ', '').lower()}-transcript», aparecerá aquí.")
        return
    st.markdown(f"📕 [{it['name']}]({it['url']})")
    if st.toggle("Mostrar la transcripción aquí", key=f"tr_show_{T}_{sel}"):
        url = OD.preview_url(it["id"])
        if url:
            components.iframe(url, height=900, scrolling=True)


def _publicados(qs):
    """Empresas europeas: tabla de lo publicado en cada presentación (trimestres, semestres y años)."""
    rows = []
    for q in qs:
        r = q.get("real") or {}
        row = {"Periodo": q["trimestre"], "Publicado": q.get("publicado")}
        for k, v in r.items():
            row[k] = v
        rows.append(row)
    df = pd.DataFrame(rows[::-1]).set_index("Periodo")
    out = pd.DataFrame(index=df.index)
    out["Publicado"] = df["Publicado"]
    for c in df.columns:
        if c == "Publicado":
            continue
        k = _kind(c)
        lab = c if k == "pct" else (f"{c} ({cur()})" if k == "ps" else f"{c} (M{cur()})")
        out[lab] = [fmt_cell(v, k) if v == v else "—" for v in pd.to_numeric(df[c], errors="coerce")]
    st.caption("Lo que publicó la empresa en cada presentación (en el formato ESEF europeo solo va el informe anual). "
               "Crecimientos frente al mismo periodo del año anterior.")
    st.dataframe(out, width="stretch", height=min(38 + 35 * len(out), 700))


def _xbrl(ca):
    if not int(ca.meta.get("cik") or 0):
        data = (storage.load(ca.fin.ticker) or {}).get("guias") or {}
        if data.get("trimestres"):
            _publicados(data["trimestres"])
        return
    try:
        df = trimestres.quarterly(sec.company_facts(int(ca.meta["cik"])), n_years=5)
    except Exception as e:  # noqa: BLE001
        st.caption(f"No he podido leer los trimestres de la SEC: {e}")
        return
    if df.empty:
        st.caption("La SEC no tiene datos trimestrales de esta empresa.")
        return
    st.markdown("#### Resultados trimestrales reales (SEC, 10-Q/10-K)")
    x = [d.strftime("%Y-%m") for d in df.index]
    fig = go.Figure()
    fig.add_bar(x=x, y=df["Ingresos"], marker_color=BLUE, name="Ingresos", text=[_fmt(v, "m") for v in df["Ingresos"]],
                textposition="outside", textfont=dict(size=9))
    fig.update_layout(template="terminal", height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    out = df.copy()
    out.index = x
    out = out.iloc[::-1]
    show_cols_table(out, height=38 + 35 * len(out),
                    kinds={"Ingresos": "m", "Beneficio neto": "m", "Resultado operativo": "m", "BPA GAAP": "ps", "Crec. interanual ingresos": "pct"})
    st.caption("Fin de trimestre fiscal. El cuarto trimestre se calcula como el año menos los tres primeros.")
