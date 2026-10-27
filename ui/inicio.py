"""Inicio: tus empresas (las de tus listas) de un vistazo.

- Cada empresa se pone o quita de una lista con un clic (las etiquetas de la derecha).
- El nombre abre la ficha en otra pestaña; al pasar el ratón por encima sale su descripción breve
  (tu «En una frase» del dossier si la tienes; si no, la actividad que declara en la SEC).
- «En cartera» es una lista más, siempre la primera.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from terminal import listas, sec, storage
from ui.common import fmt_cell, link_key, num, pct

CORTO = {"En cartera": "💼 En cartera", "Caras (esperar precio)": "Caras", "Seguir de cerca": "Seguir"}
ORDENES = {"Nombre": ("Empresa", True), "Nota financiera": ("Nota financiera", False), "PER": ("PER", True),
           "Margen de seguridad": ("Margen", False), "Capitalización": ("Capitalización (M$)", False)}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _sec_desc(cik: int) -> str:
    """Actividad declarada en la SEC (código SIC) y sede."""
    try:
        s = sec.submissions(int(cik))
    except Exception:  # noqa: BLE001
        return ""
    act = (s.get("sicDescription") or "").strip()
    b = (s.get("addresses") or {}).get("business") or {}
    sede = ", ".join(x for x in (str(b.get("city") or "").title(), b.get("stateOrCountryDescription") or b.get("stateOrCountry") or "") if x)
    partes = []
    if act:
        partes.append(f"Actividad (SEC): {act.capitalize()}")
    if sede:
        partes.append(f"Sede: {sede}")
    if s.get("website"):
        partes.append(s["website"])
    return " · ".join(partes)


def _url(t: str) -> str:
    k = link_key()
    return f"./empresa?ticker={t}" + (f"&k={k}" if k else "")


def _css():
    st.markdown("""<style>
    .ini-row { border-bottom: 1px solid #eef0f3; padding: .15rem 0; }
    a.ini-emp { font-weight: 650; color: #1f2937; text-decoration: none; font-size: 1rem; }
    a.ini-emp:hover { color: #1a5fb4; text-decoration: underline; }
    .ini-sub { color: #6b7280; font-size: .78rem; }
    .ini-desc { color: #4b5563; font-size: .8rem; line-height: 1.25; margin-top: .1rem; }
    .ini-num { text-align: right; font-variant-numeric: tabular-nums; padding-top: .35rem; }
    .ini-head { color: #6b7280; font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }
    .ini-pos { color: #15803d; } .ini-neg { color: #b91c1c; }
    .ag-grupo { color: #6b7280; font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
                margin: .55rem 0 .2rem; }
    .ag-row { display: flex; gap: .6rem; align-items: baseline; padding: .28rem 0; border-bottom: 1px solid #f1f3f6; }
    .ag-fecha { min-width: 4.6rem; font-weight: 650; color: #1f2937; font-size: .85rem; }
    .ag-dias { color: #6b7280; font-size: .72rem; display: block; font-weight: 400; }
    .ag-emp a { font-weight: 600; color: #1f2937; text-decoration: none; font-size: .88rem; }
    .ag-emp a:hover { color: #1a5fb4; text-decoration: underline; }
    .ag-ev { color: #4b5563; font-size: .78rem; }
    .ag-tag { font-size: .66rem; padding: .05rem .4rem; border-radius: 999px; margin-left: .3rem; white-space: nowrap; }
    .ag-ok { background: #e7f6ec; color: #15803d; } .ag-y { background: #eef2ff; color: #3949ab; } .ag-est { background: #f3f4f6; color: #6b7280; }
    .nt-item { padding: .45rem 0 .5rem; border-bottom: 1px solid #f1f3f6; }
    .nt-meta { color: #6b7280; font-size: .72rem; }
    .nt-tk { background: #eef2f7; color: #1f2937; font-weight: 700; border-radius: 4px; padding: 0 .35rem; margin-right: .3rem; font-size: .7rem; }
    .nt-alta { border-left: 3px solid #d97706; padding-left: .55rem; }
    .nt-tit { font-weight: 650; color: #1f2937; font-size: .9rem; line-height: 1.3; text-decoration: none; }
    a.nt-tit:hover { color: #1a5fb4; text-decoration: underline; }
    .nt-res { color: #4b5563; font-size: .8rem; line-height: 1.35; margin-top: .1rem; }
    div[class*="st-key-ini_l_"] button { padding: .1rem .55rem !important; min-height: 1.7rem !important; font-size: .8rem !important; }
    </style>""", unsafe_allow_html=True)


def page():
    from ui.prioridad import _guardados, _guardar, _listas, _universo
    _css()
    st.markdown("<span class='subtle'>INICIO</span>", unsafe_allow_html=True)
    st.markdown("# Mis empresas")
    d = _listas()
    try:
        df = _universo()
    except Exception:  # noqa: BLE001
        df = None
    gu = _guardados()
    idx = df.drop_duplicates("Ticker").set_index("Ticker") if df is not None else pd.DataFrame()

    # --- añadir una empresa
    from ui import buscador
    with st.container(border=True):
        a = st.columns([3.2, 2.2, 1])
        tickers, fmt = buscador.opciones(list(d["empresas"]))
        nueva = a[0].selectbox("Añadir empresa", tickers, index=None, format_func=fmt, key="ini_nueva",
                               placeholder="🔎 Añadir empresa: escribe nombre o ticker…", label_visibility="collapsed")
        dest = a[1].multiselect("A qué listas", d["grupos"], default=["A analizar"] if "A analizar" in d["grupos"] else None,
                                key="ini_dest", label_visibility="collapsed", placeholder="A qué listas…")
        if a[2].button("Añadir", type="primary", width="stretch", disabled=not (nueva and dest)):
            for g in dest:
                d = listas.add(d, [nueva], g)
            _guardar(d, f"{nueva} añadida a {', '.join(dest)}")
            st.rerun()

    # --- posiciones de la cartera que aún no están en «En cartera»
    try:
        abiertas = listas.posiciones_abiertas((storage.load("_CARTERA") or {}).get("movimientos", []))
    except Exception:  # noqa: BLE001
        abiertas = []
    falta = [t for t in abiertas if listas.CARTERA not in listas.lists_of(d, t)]
    if falta:
        c = st.columns([4, 1])
        c[0].caption(f"Tienes acciones de {', '.join(falta)} en tu cartera y no están en la lista «{listas.CARTERA}».")
        if c[1].button(f"Añadirlas a «{listas.CARTERA}»", width="stretch"):
            _guardar(listas.add(d, falta, listas.CARTERA), f"{len(falta)} empresa(s) en «{listas.CARTERA}»")
            st.rerun()

    if not d["empresas"]:
        st.info("Aún no tienes empresas en tus listas. Añade la primera con el buscador de arriba.")
        return

    # --- agenda: próximos resultados y noticias; tareas y recordatorios
    _agenda(d, gu, idx)
    try:
        from ui import tareas
        nombre = lambda t: (str(idx.loc[t, "Empresa"]) if t in idx.index and pd.notna(idx.loc[t, "Empresa"]) else t)  # noqa: E731
        tareas.panel_inicio(_seguidas(d, gu) + [t for t in d["empresas"] if t not in _seguidas(d, gu)], nombre, _url)
    except Exception as e:  # noqa: BLE001
        st.caption(f"No se han podido cargar las tareas: {e}")

    # --- filtro por lista y orden
    cuenta = {g: len(listas.in_list(d, g)) for g in d["grupos"]}
    opts = ["Todas"] + [g for g in d["grupos"] if cuenta[g]]
    if st.session_state.get("ini_filtro") not in opts:
        st.session_state["ini_filtro"] = listas.CARTERA if cuenta.get(listas.CARTERA) else "Todas"
    f1, f2 = st.columns([4, 1.2])
    filtro = f1.segmented_control("Lista", opts, key="ini_filtro", required=True, label_visibility="collapsed",
                                  format_func=lambda g: f"{g} ({len(d['empresas']) if g == 'Todas' else cuenta[g]})")
    orden = f2.selectbox("Ordenar por", list(ORDENES), key="ini_orden", label_visibility="collapsed",
                         format_func=lambda o: f"Ordenar por: {o.lower()}")
    ts = sorted(d["empresas"]) if filtro == "Todas" else listas.in_list(d, filtro)

    rows = []
    for t in ts:
        r = idx.loc[t] if t in idx.index else None
        res = (gu.get(t) or {}).get("resumen") or {}
        g = lambda c: (None if r is None or c not in r or pd.isna(r[c]) else r[c])  # noqa: E731
        rows.append({"Ticker": t, "Empresa": g("Empresa") or t, "Mercado": g("Mercado") or "", "Sector": g("Sector") or "",
                     "Precio": g("Precio"), "PER": g("PER"), "Nota financiera": g("Nota financiera"),
                     "Capitalización (M$)": g("Capitalización (M$)"), "CIK": g("CIK"),
                     "Valor": res.get("Valor estimado"), "Margen": res.get("Margen de seguridad"),
                     "Objetivo": (d["empresas"].get(t) or {}).get("objetivo")})
    tab = pd.DataFrame(rows)
    col, asc = ORDENES[orden]
    tab = tab.sort_values(col, ascending=asc, na_position="last", key=(lambda s: s.str.lower()) if col == "Empresa" else None)

    # --- tabla
    W = [3.0, 0.9, 0.7, 0.75, 0.95, 4.7]
    h = st.columns(W)
    for c, txt in zip(h, ["Empresa", "Precio", "PER", "Nota fin.", "Margen seg.", "Listas (clic para poner o quitar)"]):
        c.markdown(f"<div class='ini-head'>{txt}</div>", unsafe_allow_html=True)

    def _cambio(t, k):
        dd = _listas()
        _guardar(listas.set_lists(dd, t, st.session_state.get(k) or []), f"{t}: " + (", ".join(st.session_state.get(k) or [])
                                                                                     or "fuera de tus listas"))

    for rec in tab.to_dict("records"):
        r = pd.Series(rec)
        t = r.Ticker
        from terminal import descripciones
        desc = (gu.get(t) or {}).get("frase") or descripciones.corta(t, 600)
        if not desc and r.CIK is not None and not pd.isna(r.CIK) and int(r.CIK):
            desc = _sec_desc(int(r.CIK))
        if not desc:
            desc = " · ".join(x for x in (r.Sector if r.Sector != "—" else "", r.Mercado) if x)
        sub = " · ".join(x for x in (t, r.Mercado, r.Sector if r.Sector and r.Sector != "—" else "") if x)
        c = st.columns(W, vertical_alignment="center")
        c[0].markdown(f"<a class='ini-emp' href='{_url(t)}' target='_blank' title=\"{html.escape(desc or r.Empresa, quote=True)}\">"
                      f"{html.escape(str(r.Empresa))}</a><div class='ini-sub'>{html.escape(sub)}</div>"
                      + (f"<div class='ini-desc'>{html.escape(descripciones.resumir(desc, 130))}</div>" if desc else ""),
                      unsafe_allow_html=True)
        precio = "—" if r.Precio is None or pd.isna(r.Precio) else num(r.Precio, 2)
        c[1].markdown(f"<div class='ini-num'>{precio}</div>", unsafe_allow_html=True)
        c[2].markdown(f"<div class='ini-num'>{fmt_cell(r.PER, 'x')}</div>", unsafe_allow_html=True)
        c[3].markdown(f"<div class='ini-num'>{fmt_cell(r['Nota financiera'], 'ps')}</div>", unsafe_allow_html=True)
        m = r.Margen
        cls = "" if m is None or pd.isna(m) else ("ini-pos" if m > 0 else "ini-neg")
        c[4].markdown(f"<div class='ini-num {cls}'>{pct(m) if m is not None and not pd.isna(m) else '—'}</div>",
                      unsafe_allow_html=True)
        k = f"ini_l_{t}"
        st.session_state[k] = [g for g in listas.lists_of(d, t) if g in d["grupos"]]
        c[5].pills("Listas", d["grupos"], selection_mode="multi", key=k, on_change=_cambio, args=(t, k),
                   label_visibility="collapsed", wrap=True, format_func=lambda g: CORTO.get(g, g))
    st.caption("Pasa el ratón por el nombre para ver qué hace la empresa; haz clic para abrir su ficha en otra pestaña. "
               "Margen de seguridad: el de tu último análisis guardado.")


# ------------------------------------------------------------------ agenda
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _f(d) -> str:
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def _seguidas(d: dict, gu: dict) -> list[str]:
    """Empresas de tus listas (menos «Descartadas») y las que tienes analizadas."""
    ts = [t for t, e in d["empresas"].items() if [g for g in e.get("listas", []) if not g.startswith("Descartada")]]
    return list(dict.fromkeys(ts + [t for t in gu if not t.startswith("_")]))


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _fechas(items: tuple, conf_stamp: str) -> list[dict]:
    from terminal import agenda
    return agenda.proximas(dict(items))


def _agenda(d: dict, gu: dict, idx: pd.DataFrame):
    from terminal import agenda
    ts = _seguidas(d, gu)
    if not ts:
        return
    nombre = lambda t: (str(idx.loc[t, "Empresa"]) if t in idx.index and pd.notna(idx.loc[t, "Empresa"]) else t)  # noqa: E731
    cik = lambda t: (int(idx.loc[t, "CIK"]) if t in idx.index and pd.notna(idx.loc[t, "CIK"]) else 0)  # noqa: E731
    cal, nt = st.columns([1, 1.45], gap="large")

    with cal:
        st.markdown("### 📅 Calendario")
        conf = agenda.confirmadas()
        stamp = str(sorted((k, str(v.get("fecha"))) for k, v in conf.items()))
        try:
            fechas = list(_fechas(tuple((t, cik(t)) for t in ts), stamp))
        except Exception:  # noqa: BLE001
            fechas = []
        # tareas y revisiones con fecha (de Inicio o de la ficha de cada empresa)
        try:
            from datetime import date as _date
            from terminal import tareas as TA
            from ui.tareas import _items as _ti
            for x in TA.pendientes(_ti()):
                if not x.get("fecha"):
                    continue
                fd = _date.fromisoformat(x["fecha"])
                dd = (fd - _date.today()).days
                if dd <= 400:
                    fechas.append({"ticker": x.get("ticker") or "", "fecha": fd, "dias": dd, "origen": "tarea",
                                   "evento": f"{TA.TIPOS.get(x.get('tipo'), '✅')} {x['texto']}", "tipo_t": x.get("tipo")})
            fechas.sort(key=lambda r: (r["fecha"], r["ticker"]))
        except Exception:  # noqa: BLE001
            pass
        with st.container(height=430, border=True):
            if not fechas:
                st.caption("Sin fechas en los próximos meses para tus empresas.")
            hoy = pd.Timestamp.today().date()
            grupos = [("Vencidas", -1), ("Esta semana", 6), ("Próxima semana", 13), ("Este mes", 31), ("Más adelante", 10_000)]
            html_out, prev = [], -100_000
            for g, lim in grupos:
                sub = [r for r in fechas if prev < r["dias"] <= lim]
                prev = lim
                if not sub:
                    continue
                html_out.append(f"<div class='ag-grupo'>{g} · {len(sub)}</div>")
                for r in sub:
                    if r["origen"] == "tarea":
                        falta = "vencida" if r["dias"] < 0 else ("hoy" if r["dias"] == 0 else ("mañana" if r["dias"] == 1 else f"en {r['dias']} días"))
                        quien = (f"<span class='ag-emp'><a href='{_url(r['ticker'])}' target='_blank'>{html.escape(nombre(r['ticker']))}</a></span>"
                                 if r["ticker"] else "<span class='ag-emp'><b>Tarea</b></span>")
                        html_out.append(
                            f"<div class='ag-row'><div class='ag-fecha'>{_f(r['fecha'])}<span class='ag-dias'>{falta}</span></div>"
                            f"<div>{quien}<span class='ag-tag' style='background:#fff4e5;color:#b45309'>{r.get('tipo_t') or 'tarea'}</span>"
                            f"<div class='ag-ev'>{html.escape(r['evento'])}</div></div></div>")
                        continue
                    tag = {"confirmada": "<span class='ag-tag ag-ok'>✓ confirmada</span>",
                           "Yahoo Finance": "<span class='ag-tag ag-y'>Yahoo</span>"}.get(r["origen"], "<span class='ag-tag ag-est'>estimada</span>")
                    falta = "hoy" if r["dias"] == 0 else ("mañana" if r["dias"] == 1 else f"en {r['dias']} días")
                    ev = html.escape(r.get("evento") or "Resultados") + (f" · {html.escape(r['hora'])}" if r.get("hora") else "")
                    if r.get("fuente"):
                        ev = f"<a href='{html.escape(r['fuente'], quote=True)}' target='_blank' style='color:inherit'>{ev}</a>"
                    html_out.append(
                        f"<div class='ag-row'><div class='ag-fecha'>{_f(r['fecha'])}<span class='ag-dias'>{falta}</span></div>"
                        f"<div><span class='ag-emp'><a href='{_url(r['ticker'])}' target='_blank'>{html.escape(nombre(r['ticker']))}</a></span>"
                        f"{tag}<div class='ag-ev'>{r['ticker']} · {ev}</div></div></div>")
            st.markdown("".join(html_out), unsafe_allow_html=True)
            sin = [t for t in ts if t not in {r["ticker"] for r in fechas if r["origen"] != "tarea"}]
            if sin:
                st.caption("Sin fecha conocida: " + ", ".join(sin))
        st.caption("Resultados: ✓ confirmada por la empresa · Yahoo: calendario de Yahoo Finance · estimada: misma semana que "
                   "el año anterior. En naranja, tus tareas y revisiones.")

    with nt:
        st.markdown("### 📰 Noticias de tus empresas")
        n = agenda.noticias()
        items = [x for x in (n.get("items") or []) if x.get("titular")]
        c1, c2 = st.columns([1, 1.6])
        periodo = c1.segmented_control("Periodo", ["Hoy", "7 días", "30 días"], default="7 días", key="nt_periodo",
                                       label_visibility="collapsed") or "7 días"
        lim = {"Hoy": 0, "7 días": 7, "30 días": 30}[periodo]
        hoy = pd.Timestamp.today().normalize()
        items = [x for x in items if (hoy - pd.Timestamp(str(x.get("fecha", ""))[:10])).days <= lim] if items else []
        con = sorted({x.get("ticker") for x in items if x.get("ticker")})
        emp = c2.multiselect("Empresas", con, key="nt_emp", placeholder="Todas las empresas", label_visibility="collapsed",
                             format_func=lambda t: f"{nombre(t)} ({t})")
        if emp:
            items = [x for x in items if x.get("ticker") in emp]
        items.sort(key=lambda x: (str(x.get("fecha", "")), 1 if x.get("importancia") == "alta" else 0), reverse=True)
        with st.container(height=386, border=True):
            if not items:
                st.caption("Sin noticias en este periodo. Las añade cada mañana la tarea programada de noticias "
                           "(documento «_NOTICIAS» de tus datos).")
            out = []
            for x in items[:80]:
                t = x.get("ticker") or ""
                ico = agenda.TIPOS.get(x.get("tipo") or "otro", "📰")
                fd = pd.Timestamp(str(x.get("fecha"))[:10]).date()
                tit = html.escape(x.get("titular", ""))
                tit = (f"<a class='nt-tit' href='{html.escape(x['url'], quote=True)}' target='_blank'>{tit}</a>"
                       if x.get("url") else f"<span class='nt-tit'>{tit}</span>")
                meta = f"<span class='nt-tk'>{html.escape(t)}</span>{_f(fd)} · {ico} {html.escape(x.get('tipo') or 'otro')}" + \
                       (f" · {html.escape(x['fuente'])}" if x.get("fuente") else "")
                out.append(f"<div class='nt-item{' nt-alta' if x.get('importancia') == 'alta' else ''}'>"
                           f"<div class='nt-meta'>{meta}</div>{tit}"
                           + (f"<div class='nt-res'>{html.escape(x['resumen'])}</div>" if x.get("resumen") else "") + "</div>")
            st.markdown("".join(out), unsafe_allow_html=True)
        st.caption(("Actualizado: " + n["actualizado"] + " · " if n.get("actualizado") else "")
                   + "borde naranja = noticia importante para la tesis.")
