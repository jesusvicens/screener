"""Explicaciones «Cómo se lee» de cada apartado de la terminal."""
from __future__ import annotations

import streamlit as st

TEXTOS: dict[str, str] = {
    "resumen": """
**Para qué sirve:** la foto rápida de la empresa en cuatro gráficos y cinco datos, lo primero que miras antes de decidir si merece análisis.

- **Ventas, beneficio y caja libre:** las tres barras deberían crecer juntas. Si el beneficio crece y la caja libre no, el beneficio puede estar «maquillado» por partidas contables.
- **BPA y PER:** el BPA (beneficio por acción) es lo que acaba moviendo la cotización a largo plazo. El PER histórico te dice cuánto ha pagado el mercado normalmente por cada dólar de beneficio.
- **Márgenes:** márgenes altos y estables son la huella numérica de una ventaja competitiva. Si caen poco a poco, alguien le está comiendo terreno.
- **Rentabilidad del capital:** ROIC y ROE por encima del 15 % durante años indican que la empresa gana mucho con lo que tiene invertido. El «ROIC ajustado I+D» trata el I+D como inversión (más justo para tecnológicas y farmacéuticas).
""",
    "historico": """
**Para qué sirve:** ver la evolución de cualquier dato año a año, como en macrotrends.

Elige la métrica a la izquierda. La tabla muestra el valor de cada ejercicio fiscal (con su fecha de cierre real) y la variación respecto al año anterior. Fuente: los 10-K presentados en la SEC; los BPA y acciones están ajustados por splits.
""",
    "examen": """
**Para qué sirve:** tu filtro de calidad. Diez bloques: seis **cualitativos** (¿es un buen negocio, con buena dirección y futuro?) y cuatro **financieros** (¿los números lo confirman?).

- Cada pregunta da 1, 2 o 3 puntos. Nota de bloque = media de puntos / 3 × 10.
- **Nota cualitativa** = media de sus 6 bloques; **nota financiera** = media de sus 4 bloques; **nota final** = media de ambas.
- Las financieras vienen **propuestas** con 10 años de datos y criterios de Buffett; debajo de cada una ves el cálculo. Tú decides: si no estás de acuerdo, cámbiala.
- **Sin responder** cuenta 0 (como en tu Excel). **«No aplica»** no cuenta en la media: úsalo cuando la pregunta no tiene sentido para la empresa (p. ej. margen bruto en un banco).
- Pasa el ratón por el **?** de cada pregunta para ver por qué importa.
""",
    "estados": """
**Para qué sirve:** los tres estados financieros anuales tal como los presenta la empresa en sus 10-K, en millones.

- **PyG (cuenta de resultados):** lo que vende, lo que gasta y lo que gana en el año.
- **Balance:** lo que tiene (activo) y lo que debe (pasivo) a cierre de ejercicio; la diferencia es el patrimonio de los accionistas.
- **Cash Flow:** el dinero que de verdad entra y sale. El *flujo de caja libre* (operativo − capex) es lo que queda para el accionista.

Cada dato sale de una etiqueta XBRL; si una empresa cambia de etiqueta con los años, se combinan. En «De qué etiqueta XBRL sale cada dato» puedes comprobar el origen.
""",
    "eps": """
**Para qué sirve:** tu hoja «Modelo EPS»: la historia del BPA, el PER, el dividendo y el valor contable por acción, y su proyección en el escenario base.

- **Rentabilidad (BPA/precio):** la inversa del PER; lo que «rinde» la acción si todo el beneficio fuese tuyo.
- **% reservas s/ B:** la parte del beneficio que la empresa no reparte y reinvierte.
- **Control histórico del PER:** media, media sin el mejor y el peor año, y mínimo. Útil para no pagar múltiplos de euforia.
- **Buffettología:** tu modelo original. El valor contable crece al ritmo ROE × % retenido; el BPA futuro es ese valor contable × ROE y el precio futuro, ese BPA × el PER histórico.
""",
    "roic": """
**Para qué sirve:** medir cuánto gana la empresa por cada dólar que tiene invertido en el negocio, independientemente de cómo se financie.

- **Capital invertido** = deuda a largo plazo + patrimonio − caja.
- **NOPAT** = resultado operativo × (1 − tipo impositivo efectivo).
- **ROIC** = NOPAT / capital invertido medio. Por encima del 15 % sostenido suele indicar ventaja competitiva.
- **ROIC incremental:** lo que rinde el capital *nuevo* que se invierte cada año. Es lo que importa para el futuro.
- **ROIC ajustado por I+D:** trata el I+D como una inversión que se amortiza en X años (lo eliges arriba), en lugar de un gasto.
""",
    "esc_1": """
**Parámetros del inversor.** Todo lo demás depende de estos números.

- **Precio:** el de mercado (o el que escribas para probar).
- **Rentabilidad exigida r:** lo que esperas ganar con tu mejor alternativa. Sin prima de riesgo: el riesgo va en los escenarios.
- **Horizonte n:** en cuántos años mides el resultado.
- **Margen de seguridad:** la distancia mínima que quieres entre valor estimado y precio.
- **Crecimiento a largo plazo:** el ritmo de madurez (≈ PIB nominal).
- **Años hasta márgenes:** cuánto tardan los márgenes en pasar del último real al del escenario.
- **Fase:** la propone una regla (crecimiento de ventas de 3 años, ciclicidad, recuperación); puedes cambiarla.
""",
    "esc_3": """
**Escenarios.** Cuatro futuros posibles con su probabilidad. Las casillas vacías usan la propuesta de tu Excel según la fase; escribe encima para fijar tu supuesto.

- **Crecimiento año 1 → año 10:** las ventas pasan en línea recta de uno a otro.
- **Márgenes:** el bruto y el operativo a los que llega la empresa.
- **Recompras:** qué parte del flujo de caja libre se dedica a comprar acciones propias.
- **PER de salida:** si lo dejas vacío, se calcula el PER «justificado»: (1 − g/ROE) × (1 + g) / (r − g).
- **Probabilidades:** deben sumar 100 %.
""",
    "esc_4": """
**Valor futuro por escenario:** lo que valdría tu acción en el año n en cada escenario.

Valor futuro = BPA del año n × PER de salida + caja acumulada por acción + dividendos cobrados reinvertidos a r. El **umbral** es lo que necesitas para ganar tu rentabilidad exigida: precio × (1 + r)^n.
""",
    "esc_56": """
**Test de cobertura y margen de seguridad** (Parte II, El riesgo).

- **Riesgo de no compensación:** probabilidad de quedarte por debajo del umbral.
- **Riesgo asumido:** cuánto te quedas corto de media, ponderado por probabilidad. **Oportunidad asumida:** lo mismo por arriba.
- **Cobertura** = oportunidad / riesgo. Mayor que 1: compensa.
- **Valor estimado hoy** = valor futuro esperado traído a hoy con r. **Margen de seguridad** = cuánto está el precio por debajo de ese valor.
- **Precio máximo de compra** = valor estimado × (1 − margen exigido).
""",
    "esc_7": """
**Ventana de horizontes:** ¿en qué años la inversión tiene sentido en el escenario base?

Para cada año calcula el **PER de salida requerido** para ganar r. Si es menor o igual que el PER de referencia, ese año está «dentro de la ventana». Comprar caro obliga a esperar más años a que el beneficio crezca.
""",
    "esc_8": """
**Test de exposición:** traduce cada escenario a euros de tu patrimonio. Escribe tu patrimonio líquido, cuánto inviertes y la deuda ligada a la posición. La pestaña «Riesgo» lo amplía con perfiles de inversor.
""",
    "riesgo": """
**Para qué sirve:** tu método «Parte II · El riesgo» aplicado a esta empresa. No mide si la empresa es buena (eso es el examen), sino si **a este precio** la apuesta compensa el riesgo que asumes.

1. **Umbral:** lo que el precio te exige que valga la acción en el año n.
2. **Distribución:** los valores futuros de los cuatro escenarios frente a ese umbral. Las **probabilidades de prueba** engordan la cola izquierda para ver si el veredicto aguanta (paso 10: desconfiar y acotar).
3. **Test de cobertura:** oportunidad frente a riesgo; las **holguras** dicen cuánto podrías equivocarte antes de que deje de compensar.
4. **Ventana:** años en los que la inversión cuadra.
5. **Precios de compra:** el test repetido a distintos precios, para saber hasta dónde pagar.
6. **Exposición:** qué le pasaría a tu patrimonio en cada escenario según cuánto inviertes y si usas deuda. Lo importante es la **supervivencia**: que nadie pueda obligarte a vender en el peor momento.
7. **Preguntas de supervivencia:** contéstalas antes de comprar.
""",
    "filings": """
**Presentaciones en la SEC.** **10-K:** informe anual auditado (la fuente principal). **10-Q:** trimestral. **8-K:** hechos relevantes (resultados, cambios en la dirección, adquisiciones). **DEF 14A:** convocatoria de la junta, con la retribución de los directivos: revisa si cobran por crecer o por crear valor por acción.
""",
    "screener": """
**Para qué sirve:** encontrar candidatas entre todas las cotizadas de EE. UU. (~5.300 con datos) antes de abrir su ficha.

- Añade métricas en «Métricas por las que filtrar» y pon mínimo y/o máximo (los porcentajes, en %). Deja vacío para no limitar.
- **Plantillas:** filtros ya hechos; guarda los tuyos con un nombre.
- **Crecimiento medio (ventas, BPA, beneficio, FCF):** la media de los crecimientos de cada año; al lado del filtro eliges cuántos años (de 2 a 10). Si algún año la base es negativa o falta el dato, la empresa queda fuera. Compáralo con el CAGR: si se parecen, el crecimiento ha sido regular; si no, hay años raros.
- **Nota financiera:** el examen financiero completo calculado cada semana para todas las empresas. Combínalo con «Preguntas no aplicables ≤ 3» para descartar bancos y empresas con pocos datos.
- Los datos salen de la SEC (ejercicio que mejor encaja con el año natural) y los precios, capitalización y sector, del screener público de Nasdaq. Es un **primer filtro**: el análisis está en la ficha.
""",
    "lote": """
**Para qué sirve:** pasar tu modelo completo (examen financiero, cuatro escenarios, cobertura y margen de seguridad) por una lista de empresas de golpe y ordenarlas. Usa tus análisis guardados si existen; si no, las propuestas automáticas.
""",
    "cartera": """
**Para qué sirve:** llevar tus posiciones y preparar la declaración de la renta.

- **Posiciones:** acciones vivas, coste medio, valor actual y plusvalía latente en divisa y en euros (la diferencia es el efecto del tipo de cambio). Si tienes el análisis guardado, ves su valor estimado y margen de seguridad.
- **Movimientos:** una fila por operación. Importa el extracto CSV de Interactive Brokers o escríbelas a mano. Pulsa «Guardar movimientos».
- **IRPF:** ventas por FIFO (se venden primero las acciones más antiguas) en euros con el tipo del BCE de cada fecha, comisiones incluidas. Avisa de la **regla de los dos meses**: si vendes con pérdidas y recompras en ±2 meses, esa pérdida no se puede compensar ese año.
""",
}


def explica(key: str, titulo: str = "ℹ️ Cómo se lee"):
    txt = TEXTOS.get(key)
    if txt:
        with st.expander(titulo):
            st.markdown(txt)
