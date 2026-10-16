"""Tu hoja «Examen»: mismas preguntas, mismas respuestas y misma puntuación (1-3 puntos).

Bloques cualitativos (Operativo, Producto, Dirección, Estrategia, Valores y cultura, Sector):
los contestas tú. Bloques financieros (PyG, Balance, Cash Flow): la terminal te PROPONE una
respuesta calculada con los datos y te enseña el número; tú la aceptas o la cambias.

Nota del bloque = media de puntos / 3 × 10. Nota cualitativa = media de 6 bloques;
nota financiera = media de 3 bloques; nota final = media de las dos (como tu celda A2).
Las preguntas sin contestar cuentan 0, igual que en el Excel.
"""
from __future__ import annotations

from .financials import Financials

# (id, bloque, pregunta, [opción 1 punto, opción 2 puntos, opción 3 puntos])
QUESTIONS: list[tuple[str, str, str, list[str]]] = [
    ("q02", "Operativo", "¿Tiene la empresa un monopolio del consumidor fácilmente identificable?",
     ["Marca conocida pero con competencia", "Marca conocida y poca competencia", "Marca conocida con clientes cautivos (barreras de salida)"]),
    ("q03", "Operativo", "¿Es el I+D fundamental para el crecimiento?",
     ["Totalmente esencial", "Necesario para mantenerse", "No esencial pero aporta valor"]),
    ("q04", "Operativo", "¿Puede ajustar precios según la inflación?", ["No, compite por precio", "Limitadamente", "Sí, total pricing power"]),
    ("q05", "Operativo", "¿Tiene poder de compra frente a proveedores?",
     ["No, proveedores dominantes", "Tiene alternativas pero sin poder de negociación", "Sí, fuerte poder de compra"]),
    ("q06", "Operativo", "¿Tiene poder de fijación de precios frente a clientes?",
     ["No, clientes dominan", "Sí, por diferenciación", "Sí, casi sin competencia"]),
    ("q07", "Operativo", "¿Existen productos sustitutivos en recesión?", ["Sí, muchos", "Algunos pero diferenciados", "No, valor añadido muy alto"]),
    ("q08", "Producto", "¿Ofrece la empresa productos o servicios con el suficiente potencial comercial como para hacer posible un incremento considerable de las ventas durante al menos varios años?",
     ["No, los productos actuales están llegando a su madurez.", "Sí, pero requieren innovación o expansión geográfica para sostener el crecimiento.",
      "Sí, los productos tienen largo recorrido y existen nuevas categorías con potencial."]),
    ("q09", "Producto", "¿Está la dirección decidida a desarrollar productos o procesos que sigan aumentando las ventas cuando las líneas actuales se saturen?",
     ["No, la empresa se apoya en su catálogo actual sin un plan claro de innovación.", "Moderadamente, hay nuevos proyectos pero sin una estrategia definida.",
      "Sí, existe una política activa de desarrollo continuo de nuevos productos y procesos."]),
    ("q10", "Dirección", "¿Cuánto tiempo llevan los directores en la compañía? ¿Existe un líder clave?",
     ["Alta rotación o liderazgo inestable.", "Equipo con cierta continuidad pero sin Massia", "Dirección estable, con liderazgo claro y trayectoria demostrada In-house."]),
    ("q11", "Dirección", "¿Tiene la empresa un equipo directivo con una integridad incuestionable, transparencia y velando por los accionistas?",
     ["Dudas sobre la transparencia o el gobierno corporativo.", "Integridad razonable pero con áreas mejorables.", "Alta integridad y alineación con los accionistas."]),
    ("q12", "Estrategia", "¿Es la estrategia de marketing vital, innovadora y efectiva para el negocio?",
     ["Estrategia convencional, sin diferenciación.", "Estrategia sólida pero poco innovadora.", "Estrategia claramente diferenciada e innovadora, con impacto demostrado."]),
    ("q13", "Estrategia", "¿Previsión a corto o a largo plazo en relación con los beneficios?",
     ["Enfoque cortoplacista, centrado en resultados inmediatos.", "Combina visión a corto y largo plazo sin una hoja de ruta clara.",
      "Estrategia orientada al largo plazo, con objetivos definidos y consistentes."]),
    ("q14", "Estrategia", "¿Requerirá el crecimiento futuro de la empresa nuevas ampliaciones de capital?",
     ["Sí, el crecimiento depende de financiación externa o emisiones.", "Puede requerir financiación puntual o deuda moderada.",
      "No, el crecimiento es autofinanciado mediante generación de caja."]),
    ("q15", "Estrategia", "¿Han sido capaces de cumplir con objetivos pasados?",
     ["No, y no han rectificado expectativas", "Se han quedado cerca, analizado el motivo y rectificado", "Si, cumplen su plan de crecimiento."]),
    ("q16", "Valores y cultura", "¿Son los valores corporativos auténticos o una simple herramienta de marketing?",
     ["Valores principalmente cosméticos o inconsistentes con las acciones.", "Mezcla de comunicación y realidad empresarial.", "Valores auténticos e integrados en la cultura corporativa."]),
    ("q17", "Valores y cultura", "¿Se preocupa la empresa por sus trabajadores?",
     ["Alta rotación o mala reputación laboral.", "Políticas laborales aceptables pero sin programas destacados.", "Alta satisfacción, retención y desarrollo interno del talento."]),
    ("q18", "Valores y cultura", "¿Busca la empresa equilibrar rentabilidad económica y beneficio social?",
     ["Enfocada únicamente en el beneficio financiero.", "Tiene iniciativas sociales puntuales sin impacto significativo.", "Integra sostenibilidad y propósito social en su modelo de negocio."]),
    ("q19", "Sector y posicionamiento", "¿Existen barreras de entrada o ventajas competitivas estructurales en su sector?",
     ["Mercado abierto, fácil entrada de competidores.", "Algunas barreras, principalmente de marca o distribución.", "Altas barreras tecnológicas, de marca o capital intensivo."]),
    ("q20", "Sector y posicionamiento", "¿Por qué es mejor que la competencia?",
     ["Tiene ventajas parciales, pero comparables a sus rivales.", "Posee ventajas sostenibles y diferenciales claras frente a la competencia.", "No tiene competencia comparable."]),
    ("q21", "Sector y posicionamiento", "¿Es un sector intensivo en capital? (CAPEX)",
     ["Sí, requiere inversión constante", "Moderado", "No, depende de conocimiento o creatividad"]),
    ("q22", "PyG", "Calidad del crecimiento de ingresos",
     ["Crecimiento errático, cíclico o puntual", "Crecimiento relativamente estable, con componentes estructurales y coyunturales",
      "Crecimiento consistente, orgánico y apoyado en demanda recurrente o clara expansión de mercado."]),
    ("q23", "PyG", "Defensabilidad del margen bruto", ["Margen presionable", "Margen razonable", "Margen defensable"]),
    ("q24", "PyG", "Flexibilidad de la estructura de costes", ["Costes rígidos", "Costes mixtos", "Costes flexibles"]),
    ("q25", "PyG", "Margen de beneficio neto", ["Margen neto < 15%", "Margen neto entre 15% y 30%", "Margen neto > 30%"]),
    ("q26", "PyG", "Dependencia financiera y fiscal", ["Alta dependencia", "Dependencia moderada", "Baja dependencia"]),
    ("q27", "PyG", "Consistencia del beneficio neto", ["Beneficio volátil", "Beneficio estable", "Beneficio recurrente"]),
    ("q28", "Balance", "Evolución del efectivo y equivalentes", ["Disminuye", "Se mantiene", "Aumenta"]),
    ("q29", "Balance", "Deuda ajustada / Equity", ["Mayor a 0,8", "Entre 0,6 y 0,8", "Menor a 0,6"]),
    ("q30", "Balance", "Existencias vs crecimiento de ingresos", ["Desalineadas o muy cíclicas", "Ligera acumulación", "Alineadas con el crecimiento"]),
    ("q31", "Balance", "Clientes / ventas anuales", ["Mayor al 30%", "Entre 15% y 30%", "Menor al 15%"]),
    ("q32", "Balance", "Inmovilizado (PPE) sobre activo", ["Mayor al 40%", "Entre 20% y 40%", "Menor al 20%"]),
    ("q33", "Balance", "Liquidez operativa vs pasivo corriente", ["OCF insuficiente", "Cobertura parcial", "Cobertura holgada"]),
    ("q34", "Balance", "Repago deuda corto plazo con OCF", ["Más de 2 años", "Entre 1 y 2 años", "Menos de 1 año"]),
    ("q35", "Balance", "Repago deuda largo plazo con OCF", ["Más de 5 años", "Entre 3 y 5 años", "Menos de 3 años"]),
    ("q36", "Balance", "Tendencia del coeficiente de solvencia (5 años)", ["Empeora", "Se mantiene", "Mejora"]),
    ("q37", "Balance", "Política de capital (acciones propias)", ["Emite acciones", "Ni emite ni recompra", "Recompra acciones"]),
    ("q38", "Balance", "ROE", ["Menor al 15%", "Entre 15% y 25%", "Mayor al 25%"]),
    ("q39", "Cash Flow", "Flujo operativo vs beneficio neto", ["Menor que el beneficio neto", "Similar al beneficio neto", "Mayor que el beneficio neto"]),
    ("q40", "Cash Flow", "CAGR del flujo operativo vs CAGR del beneficio neto", ["Menor", "Similar", "Mayor"]),
    ("q41", "Cash Flow", "Capex sobre flujo operativo (últimos 5 años)", ["Mayor al 50%", "Entre 25% y 50%", "Menor al 25%"]),
    ("q42", "Cash Flow", "Amortiza deuda sin depender de nueva deuda", ["Emite nueva deuda para repagar", "Emite menos de lo que devuelve", "No emite nueva deuda"]),
    ("q43", "Cash Flow", "Política de capital (recompras / dilución)", ["Emite acciones", "Ni emite ni recompra", "Recompra acciones"]),
    ("q44", "Cash Flow", "¿Cuánto del flujo operativo se convierte realmente en flujo de caja libre?",
     ["FCF menor que el OCF", "FCF similar al OCF", "FCF cercano al OCF o igual al OCF"]),
]

QUALITATIVE_BLOCKS = ["Operativo", "Producto", "Dirección", "Estrategia", "Valores y cultura", "Sector y posicionamiento"]
FINANCIAL_BLOCKS = ["PyG", "Balance", "Cash Flow"]
BLOCK_SUBTITLE = {"Operativo": "¿cómo se gana dinero hoy?", "Producto": "¿hay futuro?", "Dirección": "¿se puede confiar en quien ejecuta?",
                  "Estrategia": "¿tiene plan para escalar?", "Valores y cultura": "¿la empresa puede perdurar con su cultura?",
                  "Sector y posicionamiento": "¿el viento sopla a favor?"}
Q = {q[0]: q for q in QUESTIONS}

# Umbrales de las propuestas automáticas (cámbialos aquí si quieres otro criterio).
T = {
    "growth_std_consistent": 0.06,   # desviación del crecimiento anual para «consistente»
    "gm_range_defensible": 0.05, "gm_range_reasonable": 0.10,
    "ni_ebit_low_dep": 0.75, "ni_ebit_mod_dep": 0.60,
    "cash_change": 0.10,
    "inv_gap_aligned": 0.02, "inv_gap_slight": 0.07,
    "ocf_cl_ample": 0.80, "ocf_cl_partial": 0.40,
    "solvency_change": 0.02,
    "shares_change": 0.005,
    "ocf_ni_high": 1.10, "ocf_ni_low": 0.90,
    "cagr_gap": 0.02,
    "fcf_ocf_close": 0.90, "fcf_ocf_similar": 0.75,
}


def _d(a, b):
    try:
        return a / b if (a is not None and b not in (None, 0)) else None
    except Exception:
        return None


def _cagr(last, first, n):
    if last is None or first is None or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / n) - 1


def _pct(x):
    return "n.d." if x is None else f"{x:.1%}"


def suggestions(f: Financials, stats: dict) -> dict[str, tuple[int, str]]:
    """{id_pregunta: (puntos propuestos 1-3, explicación con el dato)}. Solo bloques financieros."""
    ys = f.years
    L = ys[-1]
    y5 = ys[-6] if len(ys) >= 6 else ys[0]
    n5 = ys.index(L) - ys.index(y5)
    last5 = ys[-5:]
    s: dict[str, tuple[int, str]] = {}

    def S(k):
        return sum((f.get(k, y) or 0) for y in last5)

    growth = [g for g in stats.get("growth_series", {}).values() if g is not None]
    if growth:
        mean = sum(growth) / len(growth)
        std = (sum((g - mean) ** 2 for g in growth) / len(growth)) ** 0.5
        pts = 3 if (stats["years_down"] == 0 and std < T["growth_std_consistent"]) else 2 if stats["years_down"] <= 1 else 1
        s["q22"] = (pts, f"{stats['years_down']} años con caída de ventas; crecimiento medio {mean:.1%}, desviación {std:.1%}. «Orgánico» no se ve en los datos: revísalo.")
    if stats.get("gm_max") is not None:
        rng = stats["gm_max"] - stats["gm_min"]
        pts = 3 if rng < T["gm_range_defensible"] else 2 if rng < T["gm_range_reasonable"] else 1
        s["q23"] = (pts, f"Margen bruto entre {stats['gm_min']:.1%} y {stats['gm_max']:.1%} (rango {rng:.1%}); último {stats['gm_last']:.1%}.")
    nm = _d(f.get("net_income", L), f.get("revenue", L))
    if nm is not None:
        s["q25"] = (3 if nm > 0.30 else 2 if nm >= 0.15 else 1, f"Margen neto {L}: {nm:.1%} (media 5 años {_pct(_d(S('net_income'), S('revenue')))}).")
    ni_ebit = _d(f.get("net_income", L), f.get("operating_income", L))
    if ni_ebit is not None:
        pts = 3 if ni_ebit >= T["ni_ebit_low_dep"] else 2 if ni_ebit >= T["ni_ebit_mod_dep"] else 1
        s["q26"] = (pts, f"Beneficio neto / EBIT = {ni_ebit:.0%}: lo que se quedan intereses e impuestos.")
    nis = [f.get("net_income", y) for y in ys]
    if all(v is not None for v in nis):
        losses = sum(1 for v in nis if v <= 0)
        drops = sum(1 for a, b in zip(nis, nis[1:]) if b < a)
        pts = 1 if (losses or drops > 2) else 3 if drops == 0 else 2
        s["q27"] = (pts, f"{drops} años con caída del beneficio y {losses} con pérdidas en {len(ys)} ejercicios.")
    c0, c1 = f.get("cash_sti", y5), f.get("cash_sti", L)
    if c0 and c1 is not None:
        ch = c1 / c0 - 1
        s["q28"] = (3 if ch > T["cash_change"] else 1 if ch < -T["cash_change"] else 2, f"Caja e inversiones a corto {y5}→{L}: {ch:+.1%}.")
    debt = (f.get("st_debt", L) or 0) + (f.get("lt_debt", L) or 0)
    eq = f.get("equity", L)
    if eq is not None:
        de = _d(debt, eq) if eq > 0 else None
        pts = 1 if (eq <= 0 or (de is not None and de > 0.8)) else 2 if de >= 0.6 else 3
        s["q29"] = (pts, f"Deuda financiera / patrimonio = {('patrimonio negativo' if eq <= 0 else f'{de:.2f}')} (deuda {debt:,.0f} M). No incluye arrendamientos.")
    inv0, inv1 = f.get("inventory", y5), f.get("inventory", L)
    if not inv1:
        s["q30"] = (3, "Sin existencias relevantes en balance.")
    else:
        gi, gr = _cagr(inv1, inv0, n5), _cagr(f.get("revenue", L), f.get("revenue", y5), n5)
        if gi is not None and gr is not None:
            gap = gi - gr
            pts = 3 if gap <= T["inv_gap_aligned"] else 2 if gap <= T["inv_gap_slight"] else 1
            s["q30"] = (pts, f"Existencias crecen {gi:.1%}/año frente a ventas {gr:.1%}/año ({n5} años).")
    rs = _d(f.get("receivables", L), f.get("revenue", L))
    if rs is not None:
        s["q31"] = (3 if rs < 0.15 else 2 if rs <= 0.30 else 1, f"Clientes / ventas = {rs:.1%}.")
    pa = _d(f.get("ppe", L), f.get("total_assets", L))
    if pa is not None:
        s["q32"] = (3 if pa < 0.20 else 2 if pa <= 0.40 else 1, f"Inmovilizado material / activo = {pa:.1%}.")
    ocf = f.get("ocf", L)
    ocl = _d(ocf, f.get("current_liabilities", L))
    if ocl is not None:
        pts = 3 if ocl >= T["ocf_cl_ample"] else 2 if ocl >= T["ocf_cl_partial"] else 1
        s["q33"] = (pts, f"OCF / pasivo corriente = {ocl:.2f}. Ojo: en software el pasivo corriente incluye ingresos diferidos.")
    if ocf and ocf > 0:
        st_ = f.get("st_debt", L) or 0
        yrs = st_ / ocf
        s["q34"] = (3 if yrs < 1 else 2 if yrs <= 2 else 1, f"Deuda a corto ({st_:,.0f} M) / OCF = {yrs:.2f} años.")
        lt = f.get("lt_debt", L) or 0
        yl = lt / ocf
        s["q35"] = (3 if yl < 3 else 2 if yl <= 5 else 1, f"Deuda a largo ({lt:,.0f} M) / OCF = {yl:.2f} años.")
    elif ocf is not None:
        s["q34"] = (1, "OCF negativo: no puede repagar deuda con caja operativa.")
        s["q35"] = (1, "OCF negativo: no puede repagar deuda con caja operativa.")
    sol0 = _d(f.get("total_assets", y5), f.get("total_liabilities", y5))
    sol1 = _d(f.get("total_assets", L), f.get("total_liabilities", L))
    if sol0 and sol1:
        ch = sol1 - sol0
        pts = 3 if ch > T["solvency_change"] else 1 if ch < -T["solvency_change"] else 2
        s["q36"] = (pts, f"Activo / pasivo {y5}: {sol0:.2f} → {L}: {sol1:.2f}. (Recompras grandes bajan este ratio aunque la empresa sea sólida.)")
    shc = stats.get("share_chg5")
    if shc is not None:
        pts = 3 if shc < -T["shares_change"] else 1 if shc > T["shares_change"] else 2
        s["q37"] = (pts, f"Acciones diluidas: {shc:+.2%} anual en 5 años.")
    if stats.get("roe5") is not None:
        r5 = stats["roe5"]
        s["q38"] = (3 if r5 > 0.25 else 2 if r5 >= 0.15 else 1, f"ROE medio 5 años = {r5:.1%} (último {_pct(_d(f.get('net_income', L), eq) if eq and eq > 0 else None)}).")
    on = _d(S("ocf"), S("net_income"))
    if on is not None and S("net_income") > 0:
        pts = 3 if on > T["ocf_ni_high"] else 1 if on < T["ocf_ni_low"] else 2
        s["q39"] = (pts, f"OCF / beneficio neto (5 años) = {on:.2f}. Incluye la remuneración en acciones sumada al OCF.")
    go = _cagr(f.get("ocf", L), f.get("ocf", y5), n5)
    gn = _cagr(f.get("net_income", L), f.get("net_income", y5), n5)
    if go is not None and gn is not None:
        gap = go - gn
        pts = 3 if gap > T["cagr_gap"] else 1 if gap < -T["cagr_gap"] else 2
        s["q40"] = (pts, f"CAGR {n5} años: OCF {go:.1%} vs beneficio {gn:.1%}.")
    if S("ocf") > 0:
        co = -S("capex") / S("ocf")
        s["q41"] = (3 if co < 0.25 else 2 if co <= 0.50 else 1, f"Capex / OCF (5 años) = {co:.1%}.")
        fo = 1 - co
        pts = 3 if fo >= T["fcf_ocf_close"] else 2 if fo >= T["fcf_ocf_similar"] else 1
        s["q44"] = (pts, f"FCF / OCF (5 años) = {fo:.1%}.")
    iss, rep = S("debt_issued"), S("debt_repaid")
    if iss == 0:
        s["q42"] = (3, f"No ha emitido deuda en 5 años (ha devuelto {rep:,.0f} M).")
    else:
        s["q42"] = (2 if iss < rep else 1, f"5 años: emitida {iss:,.0f} M, devuelta {rep:,.0f} M.")
    en = S("equity_net")
    if any(f.get("equity_net", y) is not None for y in last5):
        s["q43"] = (3 if en < 0 else 1 if en > 0 else 2, f"Emisión − recompra de acciones (5 años) = {en:,.0f} M.")
    return s


def score(answers: dict[str, int | None]) -> dict:
    """answers: {id: puntos 1-3 o None}. Devuelve notas por bloque y totales (sobre 10)."""
    blocks: dict[str, dict] = {}
    for qid, block, *_ in QUESTIONS:
        b = blocks.setdefault(block, {"pts": 0, "n": 0, "answered": 0})
        b["n"] += 1
        p = answers.get(qid)
        if p:
            b["pts"] += p
            b["answered"] += 1
    for b in blocks.values():
        b["nota"] = b["pts"] / b["n"] / 3 * 10
    qual = sum(blocks[b]["nota"] for b in QUALITATIVE_BLOCKS) / len(QUALITATIVE_BLOCKS)
    fin = sum(blocks[b]["nota"] for b in FINANCIAL_BLOCKS) / len(FINANCIAL_BLOCKS)
    answered = sum(b["answered"] for b in blocks.values())
    return {"blocks": blocks, "cualitativa": qual, "financiera": fin, "final": (qual + fin) / 2,
            "respondidas": answered, "total": len(QUESTIONS),
            "cual_respondidas": sum(blocks[b]["answered"] for b in QUALITATIVE_BLOCKS)}


def claude_prompt(f: Financials, stats: dict, notes: str = "") -> str:
    """Texto para pegar en tu chat de Claude (usa tu plan, no la API) y que te ayude con el bloque cualitativo."""
    lines = [f"Ayúdame a contestar el bloque cualitativo de mi examen de inversión (estilo Fisher/Munger) para {f.name} ({f.ticker}).",
             "Para cada pregunta elige UNA de las tres respuestas literales, justifícala en 2-3 frases con hechos verificables "
             "(10-K, cartas a accionistas, resultados recientes) y dime qué evidencia me haría cambiar la respuesta. Busca información actual.",
             "", f"Contexto cuantitativo: ventas {f.years[-1]} = {f.get('revenue', f.years[-1]):,.0f} M {f.currency}; crecimiento 3 años {_pct(stats.get('g3'))}; "
             f"margen operativo {_pct(stats.get('om_last'))}; ROE medio 5 años {_pct(stats.get('roe5'))}; fase propuesta: {stats.get('phase')}.", ""]
    for qid, block, text, opts in QUESTIONS:
        if block in QUALITATIVE_BLOCKS:
            lines.append(f"[{block}] {text}")
            for i, o in enumerate(opts, 1):
                lines.append(f"   {i}) {o}")
    if notes:
        lines += ["", f"Mis notas: {notes}"]
    return "\n".join(lines)
