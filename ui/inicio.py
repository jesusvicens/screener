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

CORTO = {"En cartera": "💼 En cartera", "Caras (esperar precio)": "Caras", "Para más adelante": "Más adelante"}
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
