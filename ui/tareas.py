"""Tareas y recordatorios: bloque de Inicio y bloque de la ficha (revisiones de una empresa)."""
from __future__ import annotations

import html
from datetime import date, timedelta

import streamlit as st

from terminal import tareas as TA

PLAZOS = {"Fecha concreta": None, "En 1 mes": 1, "En 3 meses": 3, "En 6 meses": 6, "En 12 meses": 12, "En 24 meses": 24}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _f(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}" + (f" {d.year}" if d.year != date.today().year else "")


def _mas_meses(n: int) -> date:
    h = date.today()
    m = h.month - 1 + n
    y, m = h.year + m // 12, m % 12 + 1
    for d in (h.day, 28):
        try:
            return date(y, m, d)
        except ValueError:
            continue
    return h + timedelta(days=30 * n)


def _items() -> list[dict]:
    if "_tareas" not in st.session_state:
        st.session_state["_tareas"] = TA.load()
    return st.session_state["_tareas"]


def _set(items):
    st.session_state["_tareas"] = items


def _hecha(id_):
    try:
        _set(TA.marcar(id_, True))
        st.toast("Tarea hecha ✓")
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")


def _borrar(id_):
    try:
        _set(TA.borrar(id_))
        st.toast("Tarea borrada")
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")


def _deshacer(id_):
    try:
        _set(TA.marcar(id_, False))
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")


def _form(key: str, ticker: str | None = None, opciones: list[str] | None = None, fmt=None, default_tipo: str = "tarea"):
    with st.form(key, clear_on_submit=True, border=False):
        c = st.columns([2.6, 1.1, 1.3] if ticker else [2.2, 1, 1.4, 1.3])
        texto = c[0].text_input("Qué", placeholder=("Revisar la tesis…" if ticker else "Qué tienes que hacer o recordar…"))
        tipo = c[1].selectbox("Tipo", list(TA.TIPOS), index=list(TA.TIPOS).index(default_tipo),
                              format_func=lambda t: f"{TA.TIPOS[t]} {t}")
        if ticker:
            emp = ticker
            plazo = c[2].selectbox("Cuándo", list(PLAZOS), index=4)
        else:
            emp = c[2].selectbox("Empresa (opcional)", opciones or [], index=None, format_func=fmt, placeholder="Ninguna")
            plazo = c[3].selectbox("Cuándo", list(PLAZOS), index=0)
        c2 = st.columns([1.3, 3, 1])
        fecha = c2[0].date_input("Fecha (si es concreta)", value=date.today() + timedelta(days=7), format="DD/MM/YYYY")
        motivo = c2[1].text_input("Tras qué / por qué (opcional)", placeholder="p. ej. tras los resultados anuales; si el BPA no crece al 8 %…")
        c2[2].markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if c2[2].form_submit_button("Añadir", type="primary", width="stretch"):
            if not texto.strip():
                st.warning("Escribe qué tienes que hacer.")
                return
            f = fecha if PLAZOS[plazo] is None else _mas_meses(PLAZOS[plazo])
            try:
                _set(TA.add(TA.nueva(texto, f, emp, tipo, motivo)))
                st.toast(f"Añadida para el {_f(f)}")
            except Exception as e:  # noqa: BLE001
                st.error(f"No se ha podido guardar: {e}")


def _fila(x: dict, nombre=None, url=None, con_empresa: bool = True, key: str = ""):
    hoy = date.today()
    f = date.fromisoformat(x["fecha"]) if x.get("fecha") else None
    dias = (f - hoy).days if f else None
    cls = "#b91c1c" if dias is not None and dias < 0 else ("#b45309" if dias is not None and dias <= 7 else "#6b7280")
    cuando = "sin fecha" if f is None else (_f(f) + (" · vencida" if dias < 0 else (" · hoy" if dias == 0 else f" · en {dias} días")))
    emp = ""
    if con_empresa and x.get("ticker"):
        t = x["ticker"]
        lab = html.escape(nombre(t) if nombre else t)
        emp = (f"<a href='{url(t)}' target='_blank' style='color:#1f2937;font-weight:600;text-decoration:none'>{lab}</a> · "
               if url else f"<b>{lab}</b> · ")
    c = st.columns([0.07, 0.83, 0.1], vertical_alignment="center")
    c[0].checkbox("Hecha", value=False, key=f"tk_{key}{x['id']}", label_visibility="collapsed",
                  on_change=_hecha, args=(x["id"],), help="Marcar como hecha")
    c[1].markdown(
        f"<div style='line-height:1.3'>{TA.TIPOS.get(x.get('tipo'), '✅')} {emp}<span style='color:#1f2937'>{html.escape(x['texto'])}</span>"
        f"<div style='font-size:.75rem;color:{cls}'>{cuando}"
        + (f" <span style='color:#6b7280'>· {html.escape(x['motivo'])}</span>" if x.get("motivo") else "")
        + "</div></div>", unsafe_allow_html=True)
    c[2].button("🗑", key=f"tb_{key}{x['id']}", on_click=_borrar, args=(x["id"],), help="Borrar", type="tertiary")


def panel_inicio(opciones: list[str], nombre, url):
    st.markdown("### ✅ Tareas y recordatorios")
    items = _items()
    pend = TA.pendientes(items)
    hoy = date.today()
    venc = [x for x in pend if x.get("fecha") and date.fromisoformat(x["fecha"]) < hoy]
    with st.container(border=True):
        with st.expander("➕ Nueva tarea, revisión o recordatorio", expanded=False):
            _form("tarea_ini", opciones=opciones, fmt=lambda t: f"{nombre(t)} ({t})")
        if not pend:
            st.caption("No tienes tareas pendientes. Cuando la conclusión de un análisis sea «revisar en 12 meses» o «revisar tras X», "
                       "apúntala aquí o en la ficha de la empresa (Seguimiento → Mis notas y bitácora).")
        grupos = [("Vencidas", lambda d: d is not None and d < 0), ("Próximos 7 días", lambda d: d is not None and 0 <= d <= 7),
                  ("Próximo mes", lambda d: d is not None and 7 < d <= 31), ("Más adelante", lambda d: d is not None and d > 31),
                  ("Sin fecha", lambda d: d is None)]
        for g, ok in grupos:
            sub = [x for x in pend if ok((date.fromisoformat(x["fecha"]) - hoy).days if x.get("fecha") else None)]
            if not sub:
                continue
            color = "#b91c1c" if g == "Vencidas" else "#6b7280"
            st.markdown(f"<div class='ag-grupo' style='color:{color}'>{g} · {len(sub)}</div>", unsafe_allow_html=True)
            for x in sub:
                _fila(x, nombre, url, key="i")
        hechas = sorted([x for x in items if x.get("hecha")], key=lambda x: x.get("hecha_el") or "", reverse=True)[:10]
        if hechas:
            with st.expander(f"Hechas recientemente · {len(hechas)}"):
                for x in hechas:
                    c = st.columns([0.85, 0.15], vertical_alignment="center")
                    c[0].markdown(f"<span style='color:#9ca3af;text-decoration:line-through'>{html.escape(x['texto'])}</span>"
                                  f"<span style='color:#9ca3af;font-size:.75rem'> · {x.get('ticker') or ''} · hecha el {x.get('hecha_el') or ''}</span>",
                                  unsafe_allow_html=True)
                    c[1].button("Deshacer", key=f"tu_{x['id']}", on_click=_deshacer, args=(x["id"],), type="tertiary")
    if venc:
        st.caption(f"⚠️ {len(venc)} vencida(s).")


def bloque_ficha(T: str, nombre: str = ""):
    """Revisiones y tareas de una empresa, con alta rápida «Revisar en 12 meses / tras X»."""
    st.markdown("## Revisiones y tareas")
    st.caption("Si tu conclusión es «revisar en 12 meses» o «revisar tras los resultados», prográmala aquí: sale en Inicio "
               "(Tareas y recordatorios) y en su calendario.")
    pend = TA.pendientes(_items(), ticker=T)
    with st.container(border=True):
        for x in pend:
            _fila(x, con_empresa=False, key="f")
        if not pend:
            st.caption("Sin revisiones pendientes para esta empresa.")
        _form(f"tarea_ficha_{T}", ticker=T, default_tipo="revisión")
