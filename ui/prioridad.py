"""Página «Prioridad»: qué empresas analizar primero y tus listas de seguimiento."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from terminal import listas, screener, storage
from ui.ayuda import explica
from ui.common import company_url, fmt_cell, show_cols_table


@st.cache_data(ttl=300, show_spinner=False)
def _guardados() -> dict[str, dict]:
    out = {}
    try:
        for it in storage.list_all():
            t = str(it.get("ticker", "")).upper()
            if t and not t.startswith("_"):
                out[t] = {"resumen": it.get("resumen") or {}, "actualizado": it.get("actualizado"),
                          "mos": ((it.get("params") or {}).get("mos"))}
    except Exception:  # noqa: BLE001
        pass
    return out


def _listas() -> dict:
    if "_listas" not in st.session_state:
        try:
            st.session_state["_listas"] = listas.load()
        except Exception as e:  # noqa: BLE001
            st.error(f"No he podido leer tus listas: {e}")
            st.session_state["_listas"] = {"grupos": list(listas.DEFAULT_GROUPS), "empresas": {}}
    return st.session_state["_listas"]


def _guardar(d: dict, msg: str):
    try:
        listas.save(d)
        st.session_state["_listas"] = d
        st.toast(msg)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se ha podido guardar: {e}")


def _universo() -> pd.DataFrame | None:
    from ui.otras import _screen_table
    base = screener.load_base(9999)
    mk, mk_age = screener.load_market()
    if base is None or mk is None or (mk_age or 0) > 24:
        screener.sync_from_repo()
        base = screener.load_base(9999)
    if base is None:
        return None
    mk_stamp = screener.PRICES_FILE.stat().st_mtime if screener.PRICES_FILE.exists() else 0.0
    na_stamp = screener.NOTAS_FILE.stat().st_mtime if screener.NOTAS_FILE.exists() else 0.0
    df = _screen_table(screener.BASE_FILE.stat().st_mtime, mk_stamp, na_stamp)
    return screener.with_avg_growth(df)


def page():
    st.markdown("<style>.block-container{max-width:98% !important;padding-left:1.5rem;padding-right:1.5rem;}</style>",
                unsafe_allow_html=True)
    st.markdown("<span class='subtle'>PRIORIDAD · QUÉ ANALIZAR Y TUS LISTAS</span>", unsafe_allow_html=True)
    st.markdown("# Prioridad")
    explica("prioridad")
    d = _listas()
    df = _universo()
    if df is None:
        st.info("Abre primero el **Screener** una vez para descargar los datos de todas las empresas.")
        return
    gu = _guardados()
    tab_rec, tab_lis = st.tabs(["Recomendadas para analizar", "Mis listas"], key="prio_tabs")
    with tab_rec:
        _recomendadas(df, d, gu)
    with tab_lis:
        _mis_listas(df, d, gu)


# ------------------------------------------------------------------ recomendadas
def _recomendadas(df: pd.DataFrame, d: dict, gu: dict):
    c = st.columns([1, 1, 1, 1.4, 1.6])
    nmin = c[0].number_input("Nota financiera mínima", 0.0, 10.0, 7.5, 0.25)
    namax = c[1].number_input("Máx. preguntas «No aplica»", 0, 21, 3)
    vmin = c[2].number_input("Ventas mínimas (M$)", 0, 1_000_000, 300, 100)
    sectors = c[3].multiselect("Sector", sorted(s for s in df["Sector"].dropna().unique() if s != "—"), placeholder="Todos")
    orden = c[4].selectbox("Ordenar por", ["Prioridad (nota + precio)", "Nota financiera", "Crec. medio BPA", "Rent. FCF"])
    e = st.columns([1, 1, 1, 1])
    excl_listas = e[0].toggle("Ocultar las que ya están en tus listas", True)
    excl_guard = e[1].toggle("Ocultar las que ya tienes analizadas", True)
    solo_us = e[2].toggle("Solo empresas de EE. UU.", True,
                          help="Las extranjeras (ADR) a menudo reportan en otra divisa y sus ratios de precio salen sin sentido")

    m = (pd.to_numeric(df["Nota financiera"], errors="coerce") >= nmin) \
        & (pd.to_numeric(df["Preguntas no aplicables"], errors="coerce").fillna(99) <= namax) \
        & (pd.to_numeric(df["Ventas (M$)"], errors="coerce").fillna(0) >= vmin) \
        & df["Mercado"].isin(["Nasdaq", "NYSE"])
    if sectors:
        m &= df["Sector"].isin(sectors)
    if solo_us and "País" in df:
        m &= df["País"].isin(["United States", "—"])
    cand = df[m].copy()
    if excl_listas:
        cand = cand[~cand["Ticker"].isin(list(d["empresas"]))]
    if excl_guard:
        cand = cand[~cand["Ticker"].isin(list(gu))]
    cand["Prioridad"] = listas.prioridad(cand)
    key = "Prioridad" if orden.startswith("Prioridad") else orden
    cand = cand.sort_values(key, ascending=False, na_position="last")

    st.markdown(f"## {len(cand):,} candidatas")
    cols = ["Empresa", "Prioridad", "Nota financiera", "Nota PyG", "Nota Balance", "Nota Cash Flow", "Nota Asignación de capital",
            "Sector", "Capitalización (M$)", "PER", "Rent. FCF", "Crec. medio BPA", "CAGR ventas 5a", "ROE medio 5a"]
    out = cand.head(200)[["Ticker"] + [c for c in cols if c in cand]].set_index("Ticker")
    out = out.rename(columns={"Crec. medio BPA": "Crec. medio BPA 5a"})
    out["Empresa"] = [company_url(t, n) for t, n in zip(out.index, out["Empresa"])]
    kinds = {k: v for k, v in screener.METRIC_KIND.items()}
    kinds.update({"Prioridad": "ps", "Crec. medio BPA 5a": "pct"})
    show_cols_table(out, height=560, kinds={k: v for k, v in kinds.items() if k in out.columns},
                    column_config={"Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$",
                                                                          help="Abre la ficha en una pestaña nueva")})
    if len(cand) > 200:
        st.caption("Muestro las 200 primeras.")

    a = st.columns([3, 1.4, 1])
    pick = a[0].multiselect("Añadir a una lista", list(out.index), placeholder="Elige empresas de la tabla…")
    grupo = a[1].selectbox("Lista", d["grupos"], index=0, key="rec_grupo")
    if a[2].button("Añadir", type="primary", width="stretch", disabled=not pick):
        _guardar(listas.add(d, pick, grupo), f"{len(pick)} empresa(s) añadidas a «{grupo}»")
        st.rerun()


# ------------------------------------------------------------------ mis listas
def _tabla_lista(df: pd.DataFrame, d: dict, gu: dict, tickers: list[str], g: str = "") -> pd.DataFrame:
    idx = df.drop_duplicates("Ticker").set_index("Ticker")
    rows = []
    for t in tickers:
        e = d["empresas"][t]
        r = idx.loc[t] if t in idx.index else None
        res = (gu.get(t) or {}).get("resumen") or {}
        precio = r["Precio"] if r is not None else None
        precio = None if (precio is None or pd.isna(precio)) else float(precio)
        obj = e.get("objetivo")
        if obj is None and res.get("Valor estimado"):
            mos = (gu.get(t) or {}).get("mos") or 0.15
            obj_sug = res["Valor estimado"] * (1 - mos)
        else:
            obj_sug = None
        dist = (precio / obj - 1) if (precio and obj) else None
        rows.append({
            "Ticker": t, "Empresa": company_url(t, (r["Empresa"] if r is not None else t)),
            "Mover a": "—", "Añadir también a": "—",
            "Otras listas": ", ".join(x for x in e.get("listas", []) if x != g),
            "Comentario": e.get("comentario") or "", "Precio objetivo": obj,
            "Precio": precio, "Distancia al objetivo": dist,
            "Aviso": "🔔 En precio" if (dist is not None and dist <= 0) else "",
            "Nota financiera": r["Nota financiera"] if r is not None else None,
            "Nota final (guardada)": res.get("Nota final"), "Margen de seguridad (guardado)": res.get("Margen de seguridad"),
            "Precio máx. sugerido": obj_sug, "Analizada el": (gu.get(t) or {}).get("actualizado"),
            "Añadida": e.get("añadida"), "Quitar de esta lista": False,
        })
    out = pd.DataFrame(rows)
    out["Precio objetivo"] = pd.to_numeric(out["Precio objetivo"], errors="coerce").astype(float)
    # Columnas de solo lectura como texto ya formateado (el editor enseña «None» en las vacías).
    fmts = {"Precio": "ps", "Distancia al objetivo": "pct", "Nota financiera": "ps", "Nota final (guardada)": "ps",
            "Margen de seguridad (guardado)": "pct", "Precio máx. sugerido": "ps"}
    for c, k in fmts.items():
        out[c] = [fmt_cell(None if (v is None or pd.isna(v)) else float(v), k) for v in out[c]]
    for c in ("Analizada el", "Añadida"):
        out[c] = out[c].fillna("")
    return out


def _mis_listas(df: pd.DataFrame, d: dict, gu: dict):
    if not d["empresas"]:
        st.info("Aún no tienes empresas en ninguna lista. Añádelas desde «Recomendadas», desde la ficha de una empresa o desde el screener.")
    # Avisos de precio
    alerts = []
    idx = df.drop_duplicates("Ticker").set_index("Ticker")
    for t, e in d["empresas"].items():
        p = idx.loc[t, "Precio"] if t in idx.index else None
        if e.get("objetivo") and p and p <= e["objetivo"]:
            alerts.append(f"**{t}** ({p:,.2f} ≤ {e['objetivo']:,.2f})")
    if alerts:
        st.success("🔔 Han llegado a tu precio objetivo: " + ", ".join(alerts))

    grupos = d["grupos"]
    counts = {g: len(listas.in_list(d, g)) for g in grupos}
    with st.container(border=True):
        st.markdown("<div class='subtle'>Crear o borrar listas</div>", unsafe_allow_html=True)
        c = st.columns([2, 1, 2, 1])
        nueva = c[0].text_input("Nueva lista", placeholder="Nombre (p. ej. «Compounders europeos»)", label_visibility="collapsed")
        if c[1].button("Crear lista", width="stretch") and nueva.strip():
            if nueva.strip() not in d["grupos"]:
                d["grupos"].append(nueva.strip())
                _guardar(d, f"Lista «{nueva.strip()}» creada")
                st.rerun()
        vacias = [g for g in d["grupos"] if counts.get(g, 0) == 0]
        borrar = c[2].selectbox("Borrar lista vacía", vacias, index=None, placeholder="Borrar una lista vacía…", label_visibility="collapsed")
        if c[3].button("Borrar", width="stretch", disabled=not borrar):
            d["grupos"].remove(borrar)
            _guardar(d, f"Lista «{borrar}» borrada")
            st.rerun()
        st.markdown("<div class='subtle'>Añadir cualquier empresa a una lista</div>", unsafe_allow_html=True)
        a = st.columns([2, 1.4, 1])
        txt = a[0].text_input("Añadir tickers a mano", placeholder="Tickers separados por comas: COST, ASML…", label_visibility="collapsed")
        g2 = a[1].selectbox("Lista", d["grupos"], key="man_grupo", label_visibility="collapsed")
        if a[2].button("Añadir tickers", width="stretch") and txt.strip():
            ts = [t.strip().upper() for t in txt.replace(";", ",").replace(" ", ",").split(",") if t.strip()]
            _guardar(listas.add(d, ts, g2), f"{len(ts)} añadidas a «{g2}»")
            st.rerun()
    tabs = st.tabs(grupos, key="prio_listas_tabs")
    for g, tab in zip(grupos, tabs):
        with tab:
            tickers = listas.in_list(d, g)
            st.caption(f"{len(tickers)} empresa(s) en «{g}».")
            if not tickers:
                st.caption("Vacía.")
                continue
            tbl = _tabla_lista(df, d, gu, tickers, g).set_index("Ticker")
            otras = ["—"] + [x for x in grupos if x != g]
            ed = st.data_editor(
                tbl, key=f"ed_{g}", width="stretch", height=min(42 + 35 * len(tbl), 650),
                disabled=[c for c in tbl.columns if c not in ("Mover a", "Añadir también a", "Comentario", "Precio objetivo",
                                                              "Quitar de esta lista")],
                column_config={
                    "Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$"),
                    "Mover a": st.column_config.SelectboxColumn("Mover a", options=otras, help="La saca de esta lista y la mete en otra"),
                    "Añadir también a": st.column_config.SelectboxColumn("Añadir también a", options=otras,
                                                                         help="La deja aquí y la añade además a otra lista"),
                    "Comentario": st.column_config.TextColumn("Comentario", width="large"),
                    "Precio objetivo": st.column_config.NumberColumn("Precio objetivo", format="%.2f",
                                                                     help="Te aviso cuando el precio llegue aquí"),
                    "Precio máx. sugerido": st.column_config.TextColumn(help="Tu valor estimado guardado × (1 − margen de seguridad)"),
                    "Quitar de esta lista": st.column_config.CheckboxColumn("Quitar de esta lista"),
                })
            if st.button("Guardar cambios", key=f"save_{g}", type="primary"):
                for t, row in ed.iterrows():
                    e = d["empresas"].get(t)
                    if e is None:
                        continue
                    e["comentario"] = row["Comentario"] or ""
                    e["objetivo"] = None if pd.isna(row["Precio objetivo"]) else float(row["Precio objetivo"])
                    if row["Añadir también a"] and row["Añadir también a"] != "—":
                        listas.add(d, [t], row["Añadir también a"])
                    if row["Mover a"] and row["Mover a"] != "—":
                        listas.add(d, [t], row["Mover a"])
                        listas.remove_from(d, t, g)
                    elif row["Quitar de esta lista"]:
                        listas.remove_from(d, t, g)
                _guardar(d, "Listas guardadas")
                st.rerun()

    st.caption(f"Se guardan en tu almacenamiento ({storage.backend()}). Hoy: {date.today():%d-%m-%Y}.")


# ------------------------------------------------------------------ selector para la ficha y el screener
def selector_lista(ticker: str, container=None):
    """Selector «Listas» para la ficha: una empresa puede estar en varias listas a la vez."""
    box = container or st
    d = _listas()
    k = f"lista_sel_{ticker}"
    st.session_state[k] = [g for g in listas.lists_of(d, ticker) if g in d["grupos"]]  # siempre refleja lo guardado

    def _cambio():
        dd = _listas()
        sel = st.session_state[k]
        _guardar(listas.set_lists(dd, ticker, sel), f"{ticker}: " + (", ".join(sel) if sel else "fuera de tus listas"))

    box.multiselect("Listas", d["grupos"], key=k, on_change=_cambio, label_visibility="collapsed", placeholder="Añadir a mis listas…",
                    help="Puedes ponerla en varias listas a la vez (página Prioridad)")
