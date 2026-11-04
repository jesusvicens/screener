"""Página «Prioridad»: qué empresas analizar primero y tus listas de seguimiento."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from terminal import listas, screener, storage
from ui.ayuda import explica
from ui.common import alto_filas, company_url, fmt_cell, num, show_cols_table


@st.cache_data(ttl=300, show_spinner=False)
def _guardados() -> dict[str, dict]:
    out = {}
    try:
        for it in storage.list_all():
            t = str(it.get("ticker", "")).upper()
            if t and not t.startswith("_"):
                out[t] = {"resumen": it.get("resumen") or {}, "actualizado": it.get("actualizado"),
                          "mos": ((it.get("params") or {}).get("mos")), "frase": _frase(it.get("dossier") or ""),
                          "examen": it.get("examen") or {}, "motivos": it.get("cualitativo_motivos") or {}}
    except Exception:  # noqa: BLE001
        pass
    return out


def _frase(dossier: str) -> str:
    """El primer párrafo de «En una frase» del dossier (para la descripción breve)."""
    import re
    m = re.search(r"### En una frase\s*\n+(.+?)(?:\n\s*\n|\n###|$)", dossier, re.S)
    return re.sub(r"[*_`]", "", m.group(1)).strip() if m else ""


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
    st.markdown("# Prioridad")
    body()


def body():
    explica("prioridad")
    d = _listas()
    df = _universo()
    if df is None:
        st.info("Abre primero el **Screener** una vez para descargar los datos de todas las empresas.")
        return
    gu = _guardados()
    from ui import panel
    secciones = [(":material/monitoring: Panel", lambda: panel.panel(df, d, gu)),
                 (":material/list: Mis listas", lambda: _mis_listas(df, d, gu)),
                 (":material/event: Calendario de resultados", lambda: panel.calendario_tab(df, d, gu))]
    tabs = st.tabs([n for n, _ in secciones], key="prio_tabs", on_change="rerun")
    for (n, fn), tb in zip(secciones, tabs):
        if tb.open:
            with tb:
                fn()


# ------------------------------------------------------------------ recomendaciones (en el Screener)
def recomendaciones():
    """Todas las empresas con el examen cualitativo contestado (test de Claude o tu análisis), ordenadas por prioridad:
    45 % nota cualitativa + 40 % parte financiera (40 % tu nota financiera + 60 % «calidad que crece») + 15 % precio."""
    from terminal import candidatas, exam as E
    explica("recomendaciones")
    d = _listas()
    df = _universo()
    if df is None:
        st.info("Abre primero la pestaña **Screener** una vez para descargar los datos de todas las empresas.")
        return
    gu = _guardados()
    try:
        cq = candidatas.indice()
    except Exception:  # noqa: BLE001
        cq = {}
    qids = [q[0] for q in E.QUESTIONS if q[1] in E.QUALITATIVE_BLOCKS]
    info: dict[str, dict] = {}
    for t, e in cq.items():
        info[t] = {"Nota cualitativa": e.get("nota_cualitativa"), "Origen": "Claude · " + (e.get("tipo") or "test rápido"),
                   "Fecha del test": e.get("fecha"), "Veredicto": e.get("veredicto"), "Alertas": " · ".join(e.get("alertas") or []),
                   "_frase": e.get("en_una_frase"), "_bloques": e.get("notas_bloque") or {}}
    for t, g in gu.items():  # tus análisis con el cualitativo contestado mandan sobre el test de Claude
        ex = {k: v for k, v in (g.get("examen") or {}).items() if k in qids}
        if any(v for v in ex.values()):
            sc = E.score(ex)
            info[t] = {"Nota cualitativa": round(sc["cualitativa"], 2), "Origen": "Tu análisis", "Fecha del test": (g.get("actualizado") or "")[:10],
                       "Veredicto": (info.get(t) or {}).get("Veredicto"), "Alertas": (info.get(t) or {}).get("Alertas"),
                       "_frase": g.get("frase") or (info.get(t) or {}).get("_frase"),
                       "_bloques": {b: sc["blocks"][b]["nota"] for b in E.QUALITATIVE_BLOCKS}}
    if not info:
        st.info("Todavía no hay ninguna empresa con el examen cualitativo contestado. La tarea diaria de Claude puntúa 50 candidatas al día; "
                "aparecerán aquí según las vaya haciendo.")
        return
    cand = df[df["Ticker"].isin(list(info))].drop_duplicates("Ticker").copy()
    for c in ("Nota cualitativa", "Origen", "Fecha del test", "Veredicto", "Alertas"):
        cand[c] = cand["Ticker"].map(lambda t, c=c: info[t].get(c))
    for b in E.QUALITATIVE_BLOCKS:
        cand[f"Cual. {b}"] = cand["Ticker"].map(lambda t, b=b: (info[t].get("_bloques") or {}).get(b))

    c = st.columns([1, 1, 1.6, 1.4, 1.4])
    qmin = c[0].number_input("Nota cualitativa mínima", 0.0, 10.0, 0.0, 0.5)
    nmin = c[1].number_input("Nota financiera mínima", 0.0, 10.0, 0.0, 0.5)
    sectors = c[2].multiselect("Sector", sorted(s for s in cand["Sector"].dropna().unique() if s != "—"), placeholder="Todos")
    origen = c[3].multiselect("Origen", sorted(cand["Origen"].dropna().unique()), placeholder="Todos")
    orden = c[4].selectbox("Ordenar por", ["Prioridad", "Calidad que crece", "Nota cualitativa", "Nota financiera", "Margen de seguridad", "Rent. FCF"])
    e = st.columns([1, 1, 2])
    excl_listas = e[0].toggle("Ocultar las de mis listas", False)
    solo_mos = e[1].toggle("Solo con margen de seguridad positivo", False)
    m = (pd.to_numeric(cand["Nota cualitativa"], errors="coerce").fillna(0) >= qmin) \
        & (pd.to_numeric(cand["Nota financiera"], errors="coerce").fillna(0) >= nmin)
    if sectors:
        m &= cand["Sector"].isin(sectors)
    if origen:
        m &= cand["Origen"].isin(origen)
    if excl_listas:
        m &= ~cand["Ticker"].isin(list(d["empresas"]))
    if solo_mos and "Margen de seguridad" in cand:
        m &= pd.to_numeric(cand["Margen de seguridad"], errors="coerce") > 0
    cand = cand[m].copy()
    det = listas.prioridad_detalle(cand)
    for col in det.columns:
        cand[col] = det[col]
    cand = cand.sort_values(orden, ascending=False, na_position="last")

    n_claude = sum(1 for v in info.values() if v["Origen"].startswith("Claude"))
    st.markdown(f"## {num(len(cand))} empresas con el examen cualitativo")
    st.caption(f"{n_claude} puntuadas por Claude (50 nuevas cada día, en orden de prioridad) y {len(info) - n_claude} de tus análisis. "
               f"**Prioridad** (0-10) = {listas.PESO_NOTA_Q:.0%} nota financiera + {listas.PESO_CUAL_Q:.0%} nota cualitativa + "
               f"{listas.PESO_PRECIO:.0%} precio (rentabilidad por caja libre frente al resto de esta tabla: la más barata, 10). El test rápido "
               "de Claude se basa en unas pocas fuentes por empresa: es un filtro para decidir qué mirar, no un análisis completo.")
    from terminal import descripciones
    cand["Negocio"] = [info[t].get("_frase") or descripciones.para(t, gu) for t in cand["Ticker"]]
    cols = ["Empresa", "Negocio", "Prioridad", "Nota cualitativa", "Nota financiera", "Calidad que crece", "Veredicto", "Margen de seguridad", "Valor estimado",
            "Precio", "Alertas", "Origen", "Fecha del test", "Puntos por nota", "Puntos por cualitativo", "Puntos por precio"] \
        + [f"Cual. {b}" for b in E.QUALITATIVE_BLOCKS] + ["Sector", "Capitalización (M$)", "PER", "Rent. FCF", "CAGR ventas 5a", "Margen operativo",
                                                          "ROIC incremental"]
    out = cand[["Ticker"] + [x for x in cols if x in cand]].set_index("Ticker")
    out["Empresa"] = [company_url(t, n) for t, n in zip(out.index, out["Empresa"])]
    kinds = {k: v for k, v in screener.METRIC_KIND.items()}
    kinds.update({"Prioridad": "ps", "Calidad que crece": "ps", "Puntos por nota": "ps", "Puntos por cualitativo": "ps", "Puntos por precio": "ps", "Nota cualitativa": "ps",
                  "Valor estimado": "ps", **{f"Cual. {b}": "ps" for b in E.QUALITATIVE_BLOCKS}})
    ah = st.columns([3, 1.2])
    with ah[1]:
        rh = alto_filas("rec_alto")
    show_cols_table(out, height=600, kinds={k: v for k, v in kinds.items() if k in out.columns}, row_height=rh,
                    column_config={"Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$", help="Abre la ficha en una pestaña nueva"),
                                   "Negocio": st.column_config.TextColumn("Negocio", width="large"),
                                   "Veredicto": st.column_config.TextColumn("Veredicto", width="large"),
                                   "Alertas": st.column_config.TextColumn("Alertas", width="large")})
    if not out.empty:
        ver = st.selectbox("Ver las respuestas del examen de…", list(out.index), index=None, placeholder="Elige una empresa de la tabla…",
                           key="rec_ver")
        if ver:
            r = cand[cand["Ticker"] == ver].iloc[0]
            st.markdown(f"**{ver} · {r['Empresa']}** — prioridad **{r['Prioridad']:.2f}** = {r['Puntos por nota']:.2f} por nota financiera + "
                        f"{r['Puntos por cualitativo']:.2f} por cualitativa + {r['Puntos por precio']:.2f} por precio. {r['Motivo']}.")
            if (info[ver]["Origen"] or "").startswith("Claude"):
                a = candidatas.load(ver) or {}
                ans, mot = a.get("examen") or {}, a.get("motivos") or {}
                st.markdown(f"{a.get('en_una_frase') or ''}  \n**Veredicto:** {a.get('veredicto') or '—'}")
            else:
                ans, mot = gu[ver].get("examen") or {}, gu[ver].get("motivos") or {}
            from ui import cualitativo
            cualitativo.resumen_cualitativo(ver, None, ans, mot)

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
        st.info("Aún no tienes empresas en ninguna lista. Añádelas desde Screener → Recomendaciones, desde la ficha de una empresa o desde el screener.")
    # Avisos de precio
    alerts = []
    idx = df.drop_duplicates("Ticker").set_index("Ticker")
    for t, e in d["empresas"].items():
        p = idx.loc[t, "Precio"] if t in idx.index else None
        if e.get("objetivo") and p and p <= e["objetivo"]:
            alerts.append(f"**{t}** ({num(p, 2)} ≤ {num(e['objetivo'], 2)})")
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

    from ui.inicio import CORTO
    box.pills("Listas", d["grupos"], selection_mode="multi", key=k, on_change=_cambio, label_visibility="collapsed", wrap=True,
              format_func=lambda g: CORTO.get(g, g), help="Clic para poner o quitar la empresa de cada lista (puede estar en varias)")
