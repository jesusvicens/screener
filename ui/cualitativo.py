"""Pestaña «Cualitativo y documentos» de la ficha: tu análisis cualitativo y los documentos de la empresa en OneDrive."""
from __future__ import annotations

import html
import time

import streamlit as st
import streamlit.components.v1 as components

from terminal import exam as E
from terminal import onedrive as OD
from terminal import storage

ICON = {"pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗", "xlsm": "📗", "csv": "📗", "ppt": "📙", "pptx": "📙",
        "txt": "📄", "md": "📄", "htm": "🌐", "html": "🌐", "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "mp3": "🎧", "mp4": "🎬"}


def _icon(name: str) -> str:
    return ICON.get(name.rsplit(".", 1)[-1].lower(), "📄") if "." in name else "📄"


def _size(n) -> str:
    if not n:
        return ""
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# ------------------------------------------------------------------ pestaña
def _secciones(txt: str) -> tuple[str, list[tuple[str, str]]]:
    """Divide el dossier por sus títulos «### …»: (intro, [(título, contenido)])."""
    intro, secs, cur = [], [], None
    for line in (txt or "").splitlines():
        if line.startswith("### "):
            cur = [line[4:].strip(), []]
            secs.append(cur)
        elif cur is None:
            intro.append(line)
        else:
            cur[1].append(line)
    return "\n".join(intro).strip(), [(t, "\n".join(c).strip()) for t, c in secs]


def _slug(i: int) -> str:
    return f"dossier-sec-{i}"


def _dossier_doc(intro: str, secs: list[tuple[str, str]]):
    """El dossier como un documento: índice vertical a la izquierda (fijo al hacer scroll) y todo el texto seguido."""
    st.markdown("""<style>
    div[data-testid="stColumn"]:has(.st-key-dossier_indice) { position: sticky; top: 4.5rem; align-self: flex-start; z-index: 2; }
    .st-key-dossier_indice { border-right: 1px solid #e5e7eb; padding-right: .6rem; }
    .st-key-dossier_indice a { display: block; padding: .28rem .4rem; border-radius: 4px; color: #1f2937; text-decoration: none;
        font-size: .9rem; line-height: 1.25; }
    .st-key-dossier_indice a:hover { background: #eef3fa; color: #1a5fb4; }
    .st-key-dossier_indice .idx-title { font-size: .75rem; font-weight: 700; letter-spacing: .04em; color: #6b7280;
        text-transform: uppercase; margin: .2rem .4rem .5rem; }
    .dossier-sec { scroll-margin-top: 5rem; }
    .st-key-dossier_texto h4 { font-size: 1.08rem !important; font-weight: 700 !important; color: #1a5fb4; padding: .9rem 0 .2rem !important; }
    .st-key-dossier_texto h5 { font-size: 1rem !important; font-weight: 700 !important; color: #374151; padding: .6rem 0 .1rem !important; }
    .st-key-dossier_texto h6 { font-size: .95rem !important; font-weight: 600 !important; font-style: italic; color: #4b5563; }
    </style>""", unsafe_allow_html=True)
    left, right = st.columns([1, 3.6], gap="large")
    with left:
        with st.container(key="dossier_indice"):
            links = "".join(f"<a href='#{_slug(i)}'>{i + 1}. {html.escape(t)}</a>" for i, (t, _b) in enumerate(secs))
            st.markdown(f"<div class='idx-title'>Índice</div>{links}", unsafe_allow_html=True)
    with right, st.container(key="dossier_texto"):
        if intro:
            st.caption(intro.strip("*").replace("$", "\\$"))
        for i, (t, body) in enumerate(secs):
            st.markdown(f"<div id='{_slug(i)}' class='dossier-sec'></div>", unsafe_allow_html=True)
            st.markdown(f"## {i + 1}. {t}")
            st.markdown(body.replace("$", "\\$"))


def tab(T: str, ca, answers: dict, motivos: dict):
    k = f"dossier_{T}"
    # se lee siempre de lo guardado: así se ven al momento los cambios hechos fuera de la app (p. ej. por Claude)
    st.session_state[k] = (storage.load(T) or {}).get("dossier", "")
    intro, secs = _secciones(st.session_state[k])
    names = (["Dossier"] if secs else []) + ["Examen cualitativo", "Documentos", "✏️ Editar dossier"]
    tabs = st.tabs(names, key=f"cual_tabs_{T}")
    i = 0
    if secs:
        with tabs[0]:
            _dossier_doc(intro, secs)
        i = 1
    with tabs[i]:
        _resumen_cualitativo(T, ca, answers, motivos)
        if not secs:
            st.info("Aún no hay dossier para esta empresa. Pídemelo en el chat (leo tus documentos de OneDrive y el 10-K) o escríbelo "
                    "en «✏️ Editar dossier»: cada título que empiece por «### » se convierte en un apartado del índice.")
    with tabs[i + 1]:
        _documentos(T, ca)
    with tabs[i + 2]:
        _dossier_editor(T)


def _resumen_cualitativo(T, ca, answers, motivos):
    sc = E.score(answers)
    cols = st.columns(len(E.QUALITATIVE_BLOCKS) + 1)
    cols[0].metric("Nota cualitativa", f"{sc['cualitativa']:.1f}" if sc["cual_respondidas"] else "—",
                   f"{sc['cual_respondidas']} respondidas")
    for c, b in zip(cols[1:], E.QUALITATIVE_BLOCKS):
        n = sc["blocks"][b]["nota"]
        c.metric(b, f"{n:.1f}" if (n is not None and sc["blocks"][b]["answered"]) else "—")
    if not sc["cual_respondidas"]:
        st.info("Aún no has contestado el examen cualitativo de esta empresa (pestaña «Examen»). Puedes pedírmelo en el chat "
                "y lo guardo aquí con el motivo de cada respuesta.")
        return
    qs = [q for q in E.QUESTIONS if q[1] in E.QUALITATIVE_BLOCKS]
    for b in E.QUALITATIVE_BLOCKS:
        bq = [q for q in qs if q[1] == b]
        n = sc["blocks"][b]["nota"]
        with st.expander(f"{b} · {E.BLOCK_SUBTITLE.get(b, '')} — nota {n:.1f}" if n is not None else b):
            for q in bq:
                qid, _blk, text, opts = q[0], q[1], q[2], q[3] if len(q) > 3 else None
                p = answers.get(qid)
                ans = "No aplica" if p == 0 else (opts[p - 1] if (opts and p and 1 <= p <= len(opts)) else ("—" if not p else f"{p} puntos"))
                pts = "" if p in (None, 0) else f" · {p}/3"
                st.markdown(f"**{text}**  \n{ans}{pts}")
                if motivos.get(qid):
                    st.markdown(f"<div class='why'>{motivos[qid]}</div>", unsafe_allow_html=True)


def _dossier_editor(T):
    k = f"dossier_{T}"
    txt = st.session_state.get(k, "")
    st.caption("El dossier admite Markdown. Cada título que empiece por «### » es un apartado del índice.")
    new = st.text_area("Dossier", value=txt, height=520, key=f"dossier_ed_{T}", label_visibility="collapsed")
    if st.button("Guardar dossier", key=f"dossier_save_{T}", type="primary"):
        data = storage.load(T) or {}
        data["dossier"] = new
        try:
            storage.save(T, data)
            st.session_state[k] = new
            st.toast("Dossier guardado")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"No se ha podido guardar: {e}")


# ------------------------------------------------------------------ OneDrive
def _documentos(T, ca):
    if not OD.configured():
        st.info("La app aún no está conectada con tu OneDrive. Para conectarla hay que registrar una pequeña aplicación en Microsoft "
                "(una vez, unos 10 minutos) y añadir `ONEDRIVE_CLIENT_ID` en los Secrets de Streamlit. Los pasos están en "
                "`terminal/onedrive.py` y te los he dado en el chat.")
        return
    if not OD.connected():
        _login()
        return
    cfg = OD.settings()
    top = st.columns([3, 1])
    top[0].caption(f"Conectado como {cfg.get('cuenta') or 'tu cuenta'} · {'lectura y escritura del informe' if OD.can_write() else 'solo lectura'}"
                   f" · raíz: {cfg['raiz']}")
    _informe_box(T)
    with top[1].popover("Ajustes", width="stretch"):
        root = st.text_input("Carpeta raíz de tus análisis", value=cfg["raiz"], help="Ruta dentro de tu OneDrive")
        if st.button("Guardar raíz") and root:
            OD.save_root(root)
            st.session_state.pop("od_folders", None)
            st.rerun()
        if st.button("Desconectar OneDrive"):
            OD.disconnect()
            st.rerun()
    try:
        if "od_folders" not in st.session_state:
            st.session_state["od_folders"] = OD.candidate_folders(cfg["raiz"])
        folders = st.session_state["od_folders"]
    except OD.OneDriveError as e:
        st.error(str(e))
        return
    saved = cfg["carpetas"].get(T)
    guess = saved or OD.guess_folder(folders, T, ca.fin.name)
    opts = ["— Sin carpeta —"] + folders
    idx = opts.index(guess) if guess in opts else 0
    c = st.columns([3, 1])
    sel = c[0].selectbox("Carpeta de esta empresa", opts, index=idx, key=f"od_sel_{T}",
                         format_func=lambda p: p if p.startswith("—") else p.replace(cfg["raiz"] + "/", ""))
    if sel != (saved or "— Sin carpeta —") and c[1].button("Guardar carpeta", width="stretch"):
        OD.save_folder(T, None if sel.startswith("—") else sel)
        st.toast("Carpeta guardada")
        from terminal import sync_onedrive
        sync_onedrive.sync_async(T)
        st.rerun()
    if sel.startswith("—"):
        st.caption("Elige la carpeta de OneDrive donde tienes los documentos de esta empresa.")
        return
    if not saved:
        st.caption("Carpeta propuesta por el nombre de la empresa: pulsa «Guardar carpeta» para fijarla.")
    try:
        with st.spinner("Leyendo la carpeta…"):
            items = _tree_cached(sel)
    except OD.OneDriveError as e:
        st.error(str(e))
        return
    n_files = _count(items)
    st.markdown(f"**{n_files} documentos** en «{sel.rsplit('/', 1)[-1]}»")
    _render(items, T, level=0)


def _informe_box(T: str):
    """Estado del informe Word que la terminal mantiene en la carpeta de OneDrive de la empresa."""
    from terminal import sync_onedrive
    with st.container(border=True):
        st.markdown("**Informe de la terminal en OneDrive** · un Word con todo lo de esta empresa (dossier, examen, notas, "
                    "bitácora, estrategia, trimestres y valoración) que se actualiza solo cada vez que guardas o cambia el análisis.")
        if not OD.can_write():
            st.warning("Ahora la conexión es de **solo lectura**. Para que la terminal pueda guardar el informe en tu carpeta, vuelve a "
                       "conectar y acepta el permiso de escritura (solo escribe su propio fichero «… - Análisis terminal.docx»; "
                       "nunca modifica ni borra tus documentos).")
            if st.button("Dar permiso de escritura (volver a conectar)", key=f"od_rw_{T}", type="primary"):
                OD.disconnect()
                st.session_state.pop("od_flow", None)
                st.rerun()
            return
        s = sync_onedrive.status(T)
        c = st.columns([4, 1.3])
        if s:
            icon = {"subido": "✅", "al_dia": "✅", "sin_carpeta": "📁", "error": "⚠️"}.get(s.get("estado"), "ℹ️")
            txt = f"{icon} {s.get('mensaje', '')} ({s.get('cuando', '')})"
            if s.get("url"):
                txt += f" · [Abrir en OneDrive]({s['url']})"
            c[0].markdown(txt)
        else:
            c[0].caption("Comprobando el informe en segundo plano…")
        if c[1].button("Actualizar ahora", key=f"od_up_{T}", width="stretch"):
            with st.spinner("Generando el Word y subiéndolo…"):
                r = sync_onedrive.sync(T, force=True)
            (st.success if r.get("estado") == "subido" else st.warning)(r.get("mensaje", ""))


@st.cache_data(ttl=600, show_spinner=False)
def _tree_cached(path: str):
    return OD.tree(path, depth=4)


def _count(items) -> int:
    return sum(_count(i.get("children", [])) if i["folder"] else 1 for i in items)


def _render(items, T, level):
    files = [i for i in items if not i["folder"]]
    dirs = [i for i in items if i["folder"]]
    for f in files:
        c = st.columns([6, 1.2, 1, 1])
        c[0].markdown(f"{_icon(f['name'])} [{f['name']}]({f['url']})")
        c[1].caption(f["modified"])
        c[2].caption(_size(f["size"]))
        if c[3].button("Ver", key=f"pv_{f['id']}", help="Vista previa aquí mismo"):
            st.session_state[f"od_preview_{T}"] = f
    for d in dirs:
        with st.expander(f"📁 {d['name']} ({_count(d.get('children', []))})", expanded=False):
            if d.get("children"):
                _render(d["children"], T, level + 1)
            else:
                st.caption(f"Vacía o más profunda de lo que leo. [Abrir en OneDrive]({d['url']})")
    if level == 0:
        pv = st.session_state.get(f"od_preview_{T}")
        if pv:
            st.markdown(f"### Vista previa · {pv['name']}")
            url = OD.preview_url(pv["id"])
            if url:
                components.iframe(url, height=820, scrolling=True)
            else:
                st.caption(f"Este tipo de fichero no tiene vista previa. [Ábrelo en OneDrive]({pv['url']}).")


def _login():
    st.markdown("Conecta tu OneDrive para ver aquí los documentos de cada empresa y guardar en su carpeta el informe de la terminal. "
                "La app lee tus ficheros y solo **escribe su propio informe** («… - Análisis terminal.docx»).")
    flow = st.session_state.get("od_flow")
    if not flow:
        if st.button("Conectar OneDrive", type="primary"):
            try:
                st.session_state["od_flow"] = {**OD.start_login(), "t0": time.time()}
                st.rerun()
            except OD.OneDriveError as e:
                st.error(str(e))
        return
    st.markdown(f"1. Abre **[{flow['verification_uri']}]({flow['verification_uri']})**  \n"
                f"2. Escribe este código: **`{flow['user_code']}`**  \n"
                "3. Entra con tu cuenta de Microsoft y acepta. Luego pulsa «Ya he entrado».")
    c = st.columns([1, 1, 3])
    if c[0].button("Ya he entrado", type="primary"):
        res = OD.poll_login(flow["device_code"])
        if res == "ok":
            st.session_state.pop("od_flow", None)
            st.toast("OneDrive conectado")
            st.rerun()
        elif res == "pending":
            st.warning("Todavía no veo el acceso: termina el paso 3 y vuelve a pulsar.")
        else:
            st.error(res)
            st.session_state.pop("od_flow", None)
    if c[1].button("Cancelar"):
        st.session_state.pop("od_flow", None)
        st.rerun()
    if time.time() - flow.get("t0", 0) > int(flow.get("expires_in", 900)):
        st.session_state.pop("od_flow", None)
        st.warning("El código ha caducado: vuelve a pulsar «Conectar OneDrive».")
