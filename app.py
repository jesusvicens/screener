"""Terminal de análisis de empresas · uso personal.

Ejecutar en local:   streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Terminal · análisis de empresas", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

from ui.common import inject_css  # noqa: E402
from ui import empresa, otras  # noqa: E402


def _password_gate() -> bool:
    """Si defines APP_PASSWORD en los secrets, la terminal pide contraseña."""
    try:
        pwd = st.secrets.get("APP_PASSWORD")
    except Exception:
        pwd = None
    if not pwd or st.session_state.get("auth_ok"):
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
