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
    # ---------------- Análisis financiero (versión 2: criterios de Buffett, 10 años, sin dobles conteos)
    ("f01", "PyG", "Crecimiento de ventas: calidad y constancia (10 años)",
     ["Crecimiento <3 % anual o 3+ años de caída", "Crecimiento 3–8 % anual o 1–2 años de caída",
      "Crecimiento ≥8 % anual, ≤1 caída y adquisiciones <25 % del flujo operativo"]),
    ("f02", "PyG", "Nivel y estabilidad del margen bruto (10 años)",
     ["Margen medio <20 % o rango >15 pp", "Margen medio 20–40 % o rango 5–15 pp", "Margen medio ≥40 % y rango ≤5 pp"]),
    ("f03", "PyG", "Peso de la estructura: gastos comerciales y generales / margen bruto",
     ["Más del 80 %", "Entre 30 % y 80 %", "Menos del 30 %"]),
    ("f04", "PyG", "Margen neto sostenido (media y mínimo de 10 años)",
     ["Media <10 %", "Media 10–20 %", "Media ≥20 % y mínimo ≥10 %"]),
    ("f05", "PyG", "Carga financiera: intereses / resultado operativo (5 años)",
     ["Más del 30 %", "Entre 15 % y 30 %", "Menos del 15 %"]),
    ("f06", "PyG", "Consistencia del BPA (10 años)",
     ["Alguna pérdida o 3+ años de caída", "1–2 años de caída, sin pérdidas", "≤1 caída, sin pérdidas y crecimiento ≥8 % anual"]),
    ("f07", "Balance", "Años de beneficio neto para pagar toda la deuda",
     ["Más de 5 años", "Entre 3 y 5 años", "Menos de 3 años"]),
    ("f08", "Balance", "Deuda ajustada: pasivo / (patrimonio + autocartera)",
     ["Mayor a 0,8", "Entre 0,6 y 0,8", "Menor a 0,6"]),
    ("f09", "Balance", "Liquidez real: (caja + clientes) / (pasivo corriente − ingresos diferidos)",
     ["Menor a 0,5", "Entre 0,5 y 1", "1 o más"]),
    ("f10", "Balance", "Disciplina del circulante: clientes + existencias frente a ventas (5 años)",
     ["Crecen más de 5 pp/año por encima de las ventas", "Crecen hasta 5 pp/año por encima", "Crecen igual o menos que las ventas"]),
    ("f11", "Balance", "Intensidad de activos fijos: inmovilizado / activo",
     ["Mayor al 40 %", "Entre 20 % y 40 %", "Menor al 20 %"]),
    ("f12", "Balance", "Rentabilidad sostenida del capital: años (de 10) con ROE >15 % y ROIC >15 %",
     ["Menos de 5 años", "Entre 5 y 7 años", "8 años o más"]),
    ("f13", "Cash Flow", "Calidad del beneficio: (flujo operativo − remuneración en acciones) / beneficio neto (5 años)",
     ["Menor a 0,8", "Entre 0,8 y 1,0", "1,0 o más"]),
    ("f14", "Cash Flow", "Necesidad de reinversión: capex / beneficio neto (10 años)",
     ["Más del 50 %", "Entre 25 % y 50 %", "Menos del 25 %"]),
    ("f15", "Cash Flow", "Crecimiento del beneficio del propietario por acción (10 años)",
     ["Menos del 3 % anual", "Entre 3 % y 10 % anual", "10 % anual o más"]),
    ("f16", "Asignación de capital", "Rentabilidad del beneficio retenido: aumento del BPA / BPA no repartido (10 años)",
     ["Menos del 8 %", "Entre 8 % y 15 %", "15 % o más"]),
    ("f17", "Asignación de capital", "Beneficios retenidos crecientes (reservas, 10 años)",
     ["Caen", "Crecen 0–7 % anual", "Crecen ≥7 % anual"]),
    ("f18", "Asignación de capital", "Recompras eficaces: variación anual de acciones diluidas (5 años)",
     ["Las acciones aumentan", "Bajan entre 0 % y 2 % al año", "Bajan 2 % al año o más"]),
    ("f19", "Asignación de capital", "Coste real de pagar en acciones: remuneración en acciones / flujo de caja libre",
     ["Más del 25 %", "Entre 10 % y 25 %", "Menos del 10 %"]),
    ("f20", "Asignación de capital", "Financiación sana: deuda neta emitida / flujo de caja libre acumulado (10 años)",
     ["Más del 25 %", "Entre 0 % y 25 %", "No se endeuda (≤0)"]),
    ("f21", "Asignación de capital", "Crecimiento comprado: fondo de comercio e intangibles",
     ["Más del 50 % del activo o crece más que las ventas", "Entre 20 % y 50 % del activo", "Menos del 20 % del activo o estable"]),
]

QUALITATIVE_BLOCKS = ["Operativo", "Producto", "Dirección", "Estrategia", "Valores y cultura", "Sector y posicionamiento"]
FINANCIAL_BLOCKS = ["PyG", "Balance", "Cash Flow", "Asignación de capital"]
NA = "No aplica"
BLOCK_SUBTITLE = {"Operativo": "¿cómo se gana dinero hoy?", "Producto": "¿hay futuro?", "Dirección": "¿se puede confiar en quien ejecuta?",
                  "Estrategia": "¿tiene plan para escalar?", "Valores y cultura": "¿la empresa puede perdurar con su cultura?",
                  "Sector y posicionamiento": "¿el viento sopla a favor?", "PyG": "¿gana dinero de forma duradera?",
                  "Balance": "¿puede aguantar un mal momento?", "Cash Flow": "¿el beneficio se convierte en caja?",
                  "Asignación de capital": "¿qué hace la dirección con el dinero?"}
Q = {q[0]: q for q in QUESTIONS}


def _d(a, b):
    try:
        return a / b if (a is not None and b not in (None, 0)) else None
    except Exception:
        return None


def _cagr(last, first, n):
    if last is None or first is None or first <= 0 or last <= 0 or n <= 0:
        return None
    return (last / first) ** (1 / n) - 1


def _pct(x):
    return "n.d." if x is None else f"{x:.1%}"


def _band(x, lo, hi, higher_is_better=True):
    """3 bandas: devuelve 1, 2 o 3 puntos."""
    if higher_is_better:
        return 3 if x >= hi else 2 if x >= lo else 1
    return 3 if x < lo else 2 if x <= hi else 1


def suggestions(f: Financials, stats: dict) -> dict[str, tuple[int, str]]:
    """{id: (puntos, explicación)}. Puntos 0 = «No aplica» (no cuenta en la media)."""
    ys = f.years
    L = ys[-1]
    n = len(ys) - 1
    last5 = ys[-5:]
    y5 = ys[-6] if len(ys) >= 6 else ys[0]
    n5 = ys.index(L) - ys.index(y5)
    s: dict[str, tuple[int, str]] = {}

    def ser(k):
        return [f.get(k, y) for y in ys]

    def S(k, years):
        return sum((f.get(k, y) or 0) for y in years)

    rev, ni, eps = ser("revenue"), ser("net_income"), ser("eps_diluted")

    # --- PyG
    g10 = _cagr(rev[-1], rev[0], n)
    downs = sum(1 for a, b in zip(rev, rev[1:]) if a is not None and b is not None and b < a)
    acq = -S("acquisitions", ys) / S("ocf", ys) if S("ocf", ys) > 0 else 0
    if g10 is not None:
        pts = 3 if (g10 >= 0.08 and downs <= 1 and acq < 0.25) else 1 if (g10 < 0.03 or downs >= 3) else 2
        s["f01"] = (pts, f"Ventas {ys[0]}→{L}: {g10:+.1%} anual; {downs} años de caída; adquisiciones = {acq:.0%} del flujo operativo acumulado.")
    gms = [_d(f.get("gross_profit", y), f.get("revenue", y)) for y in ys]
    gms = [x for x in gms if x is not None]
    if gms and f.get("cogs", L):
        avg, rng = sum(gms) / len(gms), max(gms) - min(gms)
        pts = 3 if (avg >= 0.40 and rng <= 0.05) else 1 if (avg < 0.20 or rng > 0.15) else 2
        s["f02"] = (pts, f"Margen bruto medio {avg:.1%}, entre {min(gms):.1%} y {max(gms):.1%} (rango {rng * 100:.1f} pp). Buffett: >40 % sostenido.")
    else:
        s["f02"] = (0, "Sin coste de ventas separado (bancos, aseguradoras, algunos servicios): no aplica.")
    sga_gp = _d(S("sga", last5), S("gross_profit", last5))
    if sga_gp is not None and S("sga", last5) > 0:
        s["f03"] = (_band(sga_gp, 0.30, 0.80, False), f"Gastos comerciales y generales / margen bruto (5 años) = {sga_gp:.0%}. Buffettología: <30 % excelente, >80 % malo.")
    nms = [_d(a, b) for a, b in zip(ni, rev)]
    nms = [x for x in nms if x is not None]
    if nms:
        avg, mn = sum(nms) / len(nms), min(nms)
        pts = 3 if (avg >= 0.20 and mn >= 0.10) else 2 if avg >= 0.10 else 1
        s["f04"] = (pts, f"Margen neto medio {avg:.1%}, mínimo {mn:.1%} ({len(nms)} años).")
    ie, op = S("interest_expense", last5), S("operating_income", last5)
    if op > 0 and any(f.get("interest_expense", y) is not None for y in last5):
        s["f05"] = (_band(ie / op, 0.15, 0.30, False), f"Intereses / resultado operativo (5 años) = {ie / op:.1%}. Buffett: <15 %.")
    elif op <= 0:
        s["f05"] = (1, "Resultado operativo acumulado negativo.")
    e = [x for x in eps if x is not None]
    if len(e) >= 5:
        losses = sum(1 for x in e if x <= 0)
        edowns = sum(1 for a, b in zip(e, e[1:]) if b < a)
        ge = _cagr(e[-1], e[0], len(e) - 1)
        pts = 1 if (losses or edowns >= 3) else 3 if (edowns <= 1 and ge is not None and ge >= 0.08) else 2
        s["f06"] = (pts, f"BPA {ys[0]}→{L}: {_pct(ge)} anual; {edowns} caídas y {losses} años con pérdidas.")

    # --- Balance
    debt = (f.get("lt_debt", L) or 0) + (f.get("st_debt", L) or 0)
    ni3 = sum(x for x in ni[-3:] if x is not None) / max(1, len([x for x in ni[-3:] if x is not None]))
    if ni3 > 0:
        yrs = debt / ni3
        s["f07"] = (_band(yrs, 3, 5, False), f"Deuda financiera {debt:,.0f} M / beneficio medio 3 años {ni3:,.0f} M = {yrs:.1f} años. Buffett: <3–4 años.")
    else:
        s["f07"] = (1 if debt > 0 else 3, "Beneficio medio negativo." if debt > 0 else "Sin deuda financiera.")
    eq, tl = f.get("equity", L), f.get("total_liabilities", L)
    ts = f.get("treasury_stock", L)
    if eq is not None and tl is not None:
        if ts:
            base, how = eq + ts, f"autocartera {ts:,.0f} M"
        else:
            bb = S("buybacks", ys)
            base, how = eq + bb, f"recompras acumuladas {bb:,.0f} M (la empresa amortiza las acciones)"
        if base > 0:
            r = tl / base
            s["f08"] = (_band(r, 0.6, 0.8, False), f"Pasivo {tl:,.0f} M / (patrimonio {eq:,.0f} M + {how}) = {r:.2f}. Buffettología: <0,8.")
        else:
            s["f08"] = (1, "Patrimonio ajustado negativo.")
    cl = f.get("current_liabilities", L)
    if cl:
        dr = f.get("deferred_rev_current", L) or 0
        quick = ((f.get("cash_sti", L) or 0) + (f.get("receivables", L) or 0)) / max(cl - dr, 1e-9)
        s["f09"] = (_band(quick, 0.5, 1.0), f"(Caja + clientes) / (pasivo corriente − ingresos diferidos {dr:,.0f} M) = {quick:.2f}.")
    wc0 = (f.get("receivables", y5) or 0) + (f.get("inventory", y5) or 0)
    wc1 = (f.get("receivables", L) or 0) + (f.get("inventory", L) or 0)
    gw, gr = _cagr(wc1, wc0, n5), _cagr(f.get("revenue", L), f.get("revenue", y5), n5)
    if gw is not None and gr is not None:
        gap = gw - gr
        s["f10"] = (_band(gap, 0.0, 0.05, False) if gap > 0 else 3,
                    f"Clientes + existencias {gw:+.1%}/año frente a ventas {gr:+.1%}/año ({n5} años): diferencia {gap * 100:+.1f} pp.")
    pa = _d(f.get("ppe", L), f.get("total_assets", L))
    if pa is not None:
        s["f11"] = (_band(pa, 0.20, 0.40, False), f"Inmovilizado / activo = {pa:.1%}.")
    good = 0
    counted = 0
    for y in ys[-10:]:
        e_, n_ = f.get("equity", y), f.get("net_income", y)
        op_, tx, pt = f.get("operating_income", y), f.get("taxes", y), f.get("pretax", y)
        ic = (f.get("lt_debt", y) or 0) + (e_ or 0) - (f.get("cash_sti", y) or 0)
        if n_ is None or e_ is None or op_ is None:
            continue
        counted += 1
        t = min(max(_d(tx, pt) or 0.21, 0), 0.35) if (pt and pt > 0) else 0.21
        roe = n_ / e_ if e_ > 0 else None
        roic = op_ * (1 - t) / ic if ic > 0 else (1.0 if op_ > 0 else None)  # capital invertido negativo con beneficios = rentabilidad altísima
        if roe is not None and roic is not None and roe > 0.15 and roic > 0.15:
            good += 1
        elif roe is None and e_ <= 0 and roic is not None and roic > 0.15:
            good += 1  # patrimonio negativo por recompras: se juzga por el ROIC
    if counted:
        s["f12"] = (3 if good >= 8 else 2 if good >= 5 else 1, f"{good} de {counted} años con ROE y ROIC por encima del 15 %.")

    # --- Cash Flow
    ocf5, sbc5, ni5 = S("ocf", last5), S("sbc", last5), S("net_income", last5)
    if ni5 > 0:
        q = (ocf5 - sbc5) / ni5
        s["f13"] = (_band(q, 0.8, 1.0), f"(Flujo operativo {ocf5:,.0f} − SBC {sbc5:,.0f}) / beneficio {ni5:,.0f} (5 años) = {q:.2f}.")
    else:
        s["f13"] = (1, "Beneficio acumulado negativo en 5 años.")
    capex10, ni10 = -S("capex", ys), S("net_income", ys)
    if ni10 > 0:
        c = capex10 / ni10
        s["f14"] = (_band(c, 0.25, 0.50, False), f"Capex {capex10:,.0f} M / beneficio {ni10:,.0f} M ({len(ys)} años) = {c:.0%}. Buffett: <25 % excelente, <50 % bueno.")
    oe = []
    for y in ys:
        n_, da, cx, sb, sh = (f.get(k, y) for k in ("net_income", "da", "capex", "sbc", "shares_diluted"))
        oe.append((n_ + (da or 0) + (cx or 0) - (sb or 0)) / sh if (n_ is not None and sh) else None)
    pairs = [(i, x) for i, x in enumerate(oe) if x is not None and x > 0]
    if len(pairs) >= 2 and oe[-1] is not None:
        i0, v0 = pairs[0]
        g = _cagr(oe[-1], v0, len(ys) - 1 - i0)
        if g is None:
            s["f15"] = (1, f"Beneficio del propietario por acción negativo en {L} ({oe[-1]:.2f}).")
        else:
            s["f15"] = (_band(g, 0.03, 0.10), f"Beneficio del propietario por acción {ys[i0]}: {v0:.2f} → {L}: {oe[-1]:.2f} ({g:+.1%} anual). "
                                                "= beneficio + amortizaciones − capex − remuneración en acciones.")
    else:
        s["f15"] = (1, "Beneficio del propietario negativo o sin datos.")

    # --- Asignación de capital
    dps = [abs(f.get("dividends", y) or 0) / (f.get("shares_diluted", y) or 1) for y in ys]
    retained = sum((e_ or 0) - d_ for e_, d_ in zip(eps[:-1], dps[:-1]))
    if eps[-1] is not None and eps[0] is not None:
        if retained > 0:
            rr = (eps[-1] - eps[0]) / retained
            s["f16"] = (_band(rr, 0.08, 0.15), f"BPA {ys[0]}→{L}: +{eps[-1] - eps[0]:.2f} con {retained:.2f} de BPA retenido acumulado = {rr:.0%} "
                                               "(lo que rinde cada dólar que la empresa no reparte).")
        else:
            s["f16"] = (1, "No ha retenido beneficio (pérdidas o reparte más de lo que gana).")
    re0, re1 = f.get("retained_earnings", ys[0]), f.get("retained_earnings", L)
    if re0 is not None and re1 is not None:
        gre = _cagr(re1, re0, n) if re0 > 0 else None
        if re1 < re0:
            s["f17"] = (1, f"Reservas {ys[0]}: {re0:,.0f} M → {L}: {re1:,.0f} M (caen; ojo si es por amortizar acciones recompradas).")
        else:
            s["f17"] = (3 if (gre is not None and gre >= 0.07) else 2, f"Reservas {ys[0]}: {re0:,.0f} M → {L}: {re1:,.0f} M ({_pct(gre)} anual).")
    shc = stats.get("share_chg5")
    if shc is not None:
        s["f18"] = (3 if shc <= -0.02 else 2 if shc < 0 else 1, f"Acciones diluidas: {shc:+.2%} anual en 5 años (ya incluye la emisión por remuneración en acciones).")
    fcf_l = (f.get("ocf", L) or 0) + (f.get("capex", L) or 0)
    sbc_l = f.get("sbc", L) or 0
    if fcf_l > 0:
        r = sbc_l / fcf_l
        s["f19"] = (_band(r, 0.10, 0.25, False), f"Remuneración en acciones {sbc_l:,.0f} M / flujo de caja libre {fcf_l:,.0f} M = {r:.0%} ({L}).")
    elif sbc_l > 0:
        s["f19"] = (1, "Flujo de caja libre negativo y paga en acciones.")
    net_debt_issued = S("debt_issued", ys) - S("debt_repaid", ys)
    fcf_cum = sum((f.get("ocf", y) or 0) + (f.get("capex", y) or 0) for y in ys)
    if any(f.get("debt_net", y) is not None for y in ys) or net_debt_issued == 0:
        if fcf_cum > 0:
            r = net_debt_issued / fcf_cum
            s["f20"] = (3 if r <= 0 else 2 if r <= 0.25 else 1,
                        f"Deuda neta emitida {net_debt_issued:,.0f} M / flujo de caja libre acumulado {fcf_cum:,.0f} M ({len(ys)} años) = {r:.0%}.")
        else:
            s["f20"] = (1 if net_debt_issued > 0 else 2, "Flujo de caja libre acumulado negativo.")
    gi0, gi1 = f.get("goodwill_intangibles", y5), f.get("goodwill_intangibles", L)
    ta = f.get("total_assets", L)
    if gi1 is not None and ta:
        share = gi1 / ta
        ggi = _cagr(gi1, gi0, n5) if gi0 else None
        bought = ggi is not None and gr is not None and ggi > gr + 0.02 and share > 0.2
        pts = 1 if (share > 0.5 or bought) else 2 if share >= 0.2 else 3
        s["f21"] = (pts, f"Fondo de comercio + intangibles = {share:.0%} del activo; {_pct(ggi)} anual en {n5} años frente a ventas {_pct(gr)}.")
    elif ta:
        s["f21"] = (3, "Sin fondo de comercio ni intangibles relevantes.")

    # Bancos, aseguradoras y financieras: sin balance clasificado (corriente / no corriente) y apalancamiento estructural.
    tl_, ta_ = f.get("total_liabilities", L), f.get("total_assets", L)
    if f.get("current_assets", L) is None and tl_ and ta_ and tl_ / ta_ > 0.8:
        why = "Entidad financiera (banco, aseguradora o similar): esta métrica no tiene sentido para su modelo de negocio."
        for k in ("f02", "f03", "f05", "f08", "f09", "f10", "f11", "f12", "f13", "f14", "f19", "f20"):
            s[k] = (0, why)
    for qid, block, *_ in QUESTIONS:
        if block in FINANCIAL_BLOCKS and qid not in s:
            s[qid] = (0, "Sin datos suficientes en los 10-K (XBRL) para calcularla: queda como «No aplica». Contéstala tú si la conoces.")
    return s


def score(answers: dict[str, int | None]) -> dict:
    """answers: {id: 1-3 puntos, 0 = No aplica, None = sin responder}. Notas sobre 10.
    Sin responder cuenta 0 (como en tu Excel); «No aplica» no cuenta en la media del bloque."""
    blocks: dict[str, dict] = {}
    for qid, block, *_ in QUESTIONS:
        b = blocks.setdefault(block, {"pts": 0, "n": 0, "answered": 0, "na": 0})
        p = answers.get(qid)
        if p == 0:
            b["na"] += 1
            continue
        b["n"] += 1
        if p:
            b["pts"] += p
            b["answered"] += 1
    for b in blocks.values():
        b["nota"] = (b["pts"] / b["n"] / 3 * 10) if b["n"] else None
    qv = [blocks[b]["nota"] for b in QUALITATIVE_BLOCKS if blocks[b]["nota"] is not None]
    fv = [blocks[b]["nota"] for b in FINANCIAL_BLOCKS if blocks[b]["nota"] is not None]
    qual = sum(qv) / len(qv) if qv else 0.0
    fin = sum(fv) / len(fv) if fv else 0.0
    answered = sum(b["answered"] + b["na"] for b in blocks.values())
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
