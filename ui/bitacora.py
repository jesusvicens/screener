"""Bitácora de cada empresa: notas con fecha (tesis, resultados, compras, ventas…) para ver cómo cambia tu opinión."""
from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from terminal import storage

TIPOS = {"Tesis": "🧭", "Resultados": "📊", "Compra": "🟢", "Venta": "🔴", "Idea": "💡", "Riesgo": "⚠️", "Dirección": "👤", "Otro": "📝"}


def _load(T: str) -> list[dict]:
    return list((storage.load(T) or {}).get("bitacora") or [])


def _save(T: str, entries: list[dict]) -> bool:
    data = storage.load(T) or {}
    data["bitacora"] = entries
    try:
        storage.save(T, data)
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")
        return False


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("bitacora")
    try:
        from ui import conclusion as CO
        st.markdown("## Mi conclusión")
        st.caption("Tu opinión en una palabra y en dos o tres frases. Sale en «Mis análisis», en la cabecera de la ficha y en tus listas.")
        CO.editor(T, (storage.load(T) or {}).get("conclusion"), key=f"concl_{T}")
    except Exception as e:  # noqa: BLE001
        st.caption(f"No se ha podido cargar la conclusión: {e}")
    try:
        from ui import tareas
        tareas.bloque_ficha(T)
    except Exception as e:  # noqa: BLE001
        st.caption(f"No se han podido cargar las tareas: {e}")
    st.markdown("## Bitácora")
    st.caption("Apunta con fecha lo que vas pensando: la tesis inicial, qué cambió en cada resultado, por qué compraste o vendiste. "
               "Se guarda al momento (no hace falta «Guardar análisis»).")
    k = f"bita_{T}"
    if k not in st.session_state:
        st.session_state[k] = _load(T)
    entries = st.session_state[k]
    with st.form(f"bita_form_{T}", clear_on_submit=True, border=True):
        c = st.columns([1, 1.2, 1])
        f = c[0].date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        tipo = c[1].selectbox("Tipo", list(TIPOS), format_func=lambda x: f"{TIPOS[x]} {x}")
        precio = c[2].number_input("Precio ese día (opcional)", min_value=0.0, value=float(ca.params.price or 0.0), step=0.5)
        texto = st.text_area("Nota", height=110, placeholder="Qué ha pasado y qué piensas ahora…")
        if st.form_submit_button("Añadir a la bitácora", type="primary") and texto.strip():
            entries = entries + [{"id": uuid.uuid4().hex[:10], "fecha": f.isoformat(), "tipo": tipo, "texto": texto.strip(),
                                  "precio": precio or None}]
            if _save(T, entries):
                st.session_state[k] = entries
                st.toast("Nota añadida")
                st.rerun()
    if not entries:
        st.info("Aún no hay notas. La primera suele ser la tesis: por qué te interesa la empresa y qué tendría que pasar para que te equivoques.")
        return
    filtro = st.multiselect("Filtrar por tipo", list(TIPOS), key=f"bita_f_{T}", placeholder="Todos los tipos")
    P = ca.params.price
    for e in sorted(entries, key=lambda x: x["fecha"], reverse=True):
        if filtro and e["tipo"] not in filtro:
            continue
        d = date.fromisoformat(e["fecha"])
        chg = (f" · precio entonces {e['precio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
               + (f" ({(P / e['precio'] - 1) * 100:+.1f}% hasta hoy)".replace(".", ",") if (P and e.get("precio")) else "")) if e.get("precio") else ""
        with st.container(border=True):
            c = st.columns([8, 1])
            c[0].markdown(f"**{TIPOS.get(e['tipo'], '📝')} {e['tipo']}** · {d:%d/%m/%Y}<span class='subtle'>{chg}</span>", unsafe_allow_html=True)
            if c[1].button("Borrar", key=f"bita_del_{e['id']}", width="stretch"):
                rest = [x for x in entries if x["id"] != e["id"]]
                if _save(T, rest):
                    st.session_state[k] = rest
                    st.rerun()
            st.markdown(e["texto"].replace("$", "\\$"))
