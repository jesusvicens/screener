"""Tu conclusión sobre cada empresa analizada: opinión en una palabra + resumen breve.

Se guarda en el JSON de la empresa, clave «conclusion»:
    {"opinion": "Esperar precio", "texto": "…", "fecha": "2026-10-27", "origen": "yo" | "borrador"}
«borrador» = propuesta de Claude sacada de tu análisis, pendiente de que la revises.
"""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from terminal import storage

OPINIONES = {
    "Comprar": ("#15803d", "#e7f6ec"),
    "Mantener": ("#1d4ed8", "#e8efff"),
    "Esperar precio": ("#b45309", "#fff4e5"),
    "Seguir de cerca": ("#6d28d9", "#f1ebff"),
    "Por analizar": ("#4b5563", "#f3f4f6"),
    "Descartar": ("#b91c1c", "#fdecec"),
}


def badge(op: str | None) -> str:
    if not op:
        return ""
    fg, bg = OPINIONES.get(op, ("#4b5563", "#f3f4f6"))
    return (f"<span style='background:{bg};color:{fg};font-weight:700;font-size:.75rem;border-radius:999px;"
            f"padding:.1rem .55rem;white-space:nowrap'>{html.escape(op)}</span>")


def _md(t: str) -> str:
    import re
    t = html.escape(t or "")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t).replace("$", "&#36;")


def html_bloque(c: dict | None) -> str:
    if not c or not (c.get("texto") or c.get("opinion")):
        return ""
    extra = " <span style='color:#9ca3af;font-size:.72rem'>(borrador: revísala)</span>" if c.get("origen") == "borrador" else ""
    fecha = f" <span style='color:#9ca3af;font-size:.72rem'>· {c['fecha']}</span>" if c.get("fecha") else ""
    return f"{badge(c.get('opinion'))} <span>{_md(c.get('texto', ''))}</span>{fecha}{extra}"


def guardar(T: str, opinion: str, texto: str) -> bool:
    data = storage.load(T) or {}
    data["conclusion"] = {"opinion": opinion, "texto": texto.strip(), "fecha": date.today().isoformat(), "origen": "yo"}
    try:
        storage.save(T, data)
        if f"saved_{T}" in st.session_state:
            st.session_state[f"saved_{T}"]["conclusion"] = data["conclusion"]
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")
        return False


def editor(T: str, actual: dict | None, key: str):
    actual = actual or {}
    with st.form(key, border=False):
        c = st.columns([1.2, 4])
        ops = list(OPINIONES)
        op = c[0].selectbox("Opinión", ops, index=ops.index(actual["opinion"]) if actual.get("opinion") in ops else 4)
        tx = c[1].text_area("Mi conclusión (2-3 frases)", value=actual.get("texto", ""), height=90,
                            placeholder="Qué opinas y qué tendría que pasar para comprar, mantener o vender…")
        if st.form_submit_button("Guardar conclusión", type="primary"):
            if guardar(T, op, tx):
                st.toast("Conclusión guardada")
                st.rerun()
