"""Terminal de análisis de empresas · uso personal.

Ejecutar en local:   streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Terminal · análisis de empresas", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

import sys  # noqa: E402


def _import_ui():
    """Al subir código nuevo, Streamlit recarga los módulos y a veces la importación falla con KeyError('ui')
    (se queda a medias en sys.modules). En ese caso se limpian los módulos de la app y se importan de nuevo."""
    try:
        from ui import common, empresa, otras
    except KeyError:
        for m in [k for k in list(sys.modules) if k.split(".")[0] in ("ui", "terminal")]:
            sys.modules.pop(m, None)
        from ui import common, empresa, otras
    return common, empresa, otras


_common, empresa, otras = _import_ui()
inject_css, link_key = _common.inject_css, _common.link_key


def _password_gate() -> bool:
    """Si defines APP_PASSWORD en los secrets, la terminal pide contraseña.

    Los enlaces que abren fichas en otra pestaña llevan una llave (?k=…) derivada de la contraseña,
    para no tener que volver a escribirla en cada pestaña nueva.
    """
    try:
        pwd = st.secrets.get("APP_PASSWORD")
    except Exception:
        pwd = None
    if not pwd or st.session_state.get("auth_ok"):
        return True
    k = st.query_params.get("k")
    if k and k == link_key():
        st.session_state["auth_ok"] = True
        del st.query_params["k"]
        return True
    st.markdown("# ▣ Terminal")
    p = st.text_input("Contraseña", type="password")
    if p and p == pwd:
        st.session_state["auth_ok"] = True
        st.rerun()
    elif p:
        st.error("Contraseña incorrecta.")
    return False


inject_css()
if _password_gate():
    pg_emp = st.Page(empresa.page, title="Empresa", icon=":material/domain:", url_path="empresa", default=True)
    pg_scr = st.Page(otras.screener_page, title="Screener", icon=":material/filter_alt:", url_path="screener")
    pg_lot = st.Page(otras.lote_page, title="Lote", icon=":material/playlist_play:", url_path="lote")
    pg_mis = st.Page(otras.mis_analisis_page, title="Mis análisis", icon=":material/bookmark:", url_path="mis-analisis")
    pg_car = st.Page(otras.cartera_page, title="Cartera", icon=":material/account_balance_wallet:", url_path="cartera")
    st.session_state["_page_empresa"], st.session_state["_page_lote"] = pg_emp, pg_lot
    nav = st.navigation([pg_emp, pg_scr, pg_car, pg_lot, pg_mis], position="top")
    nav.run()
