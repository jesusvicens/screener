# Terminal de análisis de empresas

Terminal personal para analizar cotizadas de EE. UU. con tu propio modelo (el Excel de Adobe convertido en motor de cálculo).

- **Datos de ~10.000 empresas** desde la API gratuita de la SEC (EDGAR/XBRL): PyG, balance y cash flow anuales de los 10-K, hasta 15 años.
- **Precios** de Yahoo Finance (con Stooq de respaldo). Si fallan, escribes el precio a mano.
- **Tu análisis se calcula al abrir cada empresa**: no hay nada precalculado. Si quieres pasarlo por muchas a la vez, está la página *Lote*.
- **Coste cero**: sin API de Claude ni suscripciones de datos.

## Qué hay dentro

| Página | Qué hace |
|---|---|
| **Empresa** | Ficha con tus hojas: Examen (43 preguntas, misma puntuación), Estados financieros, Modelo EPS (+ tu modelo de Buffettología), ROIC (+ I+D capitalizado), Escenarios y valoración (fase, 4 escenarios, proyección a 10 años, test de cobertura, margen de seguridad, ventana de horizontes, test de exposición), presentaciones en la SEC y notas. Botón para guardar y exportar a Excel. |
| **Riesgo** (pestaña de la ficha) | Tu método «Parte II · El riesgo»: BPA y precio de salida a 5 y 10 años, distribución de valores futuros, test de cobertura con probabilidades de prueba (cola izquierda engordada), ventana de horizontes, valor estimado y tabla de precios de compra, test de exposición por perfil de inversor (editable), preguntas de supervivencia y conclusión redactada. |
| **Screener** | Estilo macrotrends sobre **todas** las cotizadas (~5.300 con datos): 47 métricas (crecimientos de ventas, BPA, beneficio, FCF y patrimonio a 1/3/5 años, consistencia, márgenes, ROE/ROA/ROIC, salud, política de capital y valoración: PER, PEG, P/Ventas, P/VC, P/FCF, EV/EBIT, EV/EBITDA, rentabilidades). Filtros con mínimo y máximo por cualquier métrica, sector, industria, mercado y búsqueda; plantillas (Fisher/Munger, crecimiento de BPA, compounders baratos…) y las tuyas propias; columnas y orden a elegir; CSV; enviar a la ficha o al lote. Fundamentales de la SEC (≈1-2 min, caché semanal); precios, capitalización y sector del screener público de Nasdaq (una llamada, caché diaria). |
| **Lote** | Pasa el modelo completo por una lista de tickers (o por el resultado del screener) y ordena por margen de seguridad. |
| **Mis análisis** | Las empresas que has guardado, con su nota y su valoración del día en que guardaste. |

### Cómo funciona el examen
- Bloques cualitativos (Operativo, Producto, Dirección, Estrategia, Valores, Sector): los contestas tú. En la pestaña hay un texto listo para pegar en tu chat de Claude y trabajarlos ahí.
- Bloques financieros (PyG, Balance, Cash Flow): la terminal **propone** la respuesta con los datos y te enseña el número; tú la cambias si no estás de acuerdo. Los umbrales están en `terminal/exam.py` (diccionario `T`).

### Escenarios
Las casillas vacías usan la propuesta por fase de tu Excel (la ves en gris). Escribes encima para fijar tu supuesto y la borras para volver a la propuesta. El escenario **Desastre**, que en el Excel daba `#REF!`, aquí se calcula.

## Ponerla online (gratis, solo para ti)

1. Sube esta carpeta a un repositorio **privado** de GitHub (puede ser tu repo `screener`).
2. Entra en <https://share.streamlit.io> con tu cuenta de GitHub → **Create app** → elige el repo, rama `main`, archivo `app.py`.
3. En **Advanced settings → Secrets** pega (cambiando los valores):
   ```toml
   SEC_USER_AGENT = "Tu Nombre tuemail@gmail.com"   # la SEC exige identificarse
   APP_PASSWORD   = "una-contraseña"                # opcional: pide contraseña al entrar
   GITHUB_TOKEN   = "github_pat_..."                # para guardar tus análisis en el repo
   GITHUB_REPO    = "tuusuario/screener"
   ```
   El token se crea en GitHub → Settings → Developer settings → *Fine-grained tokens*, con acceso solo a ese repo y permiso **Contents: Read and write**.
4. **Deploy**. En *Settings → Sharing* de la app puedes dejarla visible solo para tu email.

Sin `GITHUB_TOKEN`, los análisis se guardan en el disco del servidor y se pierden cuando Streamlit reinicia la app. Con el token, cada guardado es un commit en `data/analisis/` y tienes el historial de versiones.

## Ejecutarla en tu ordenador
```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Tu Nombre tuemail@gmail.com"
streamlit run app.py
```

## Importar tus Excel antiguos
```bash
python importar_excel.py "ADOBE - analisis financer 2026.xlsx" ADBE
```
Copia las respuestas del examen, la nota de seguimiento, tus parámetros (r, horizonte, margen de seguridad…) y la parte de riesgo (probabilidades y precios de prueba, caída intermedia, garantía mínima, perfiles de inversor). Adobe ya viene importado con la versión nueva del Excel.

## Límites a tener en cuenta
- Solo empresas que presentan en la SEC (EE. UU. y extranjeras con ADR que presentan 20-F en XBRL). Los datos estructurados empiezan en ~2009.
- Algunas empresas con varias clases de acciones (p. ej. Visa) no publican BPA consolidado en XBRL: la ficha te pide el número de acciones a mano.
- En el screener, las empresas que reportan en otra divisa (p. ej. RMB) dan un PER sin sentido; la ficha individual muestra la divisa.
- La «Deuda a largo plazo» no incluye arrendamientos operativos.

## Estructura
```
app.py                 navegación y contraseña
terminal/sec.py        API de la SEC (universo, companyfacts, frames, presentaciones)
terminal/financials.py XBRL → PyG / Balance / Cash Flow (con ajuste por splits)
terminal/prices.py     precios y precio medio por ejercicio
terminal/analysis.py   Modelo EPS, ROIC, fase, escenarios, proyección, valoración
terminal/riesgo.py     análisis de riesgo (Parte II)
terminal/exam.py       examen, propuestas automáticas y puntuación
terminal/screener.py   screener de todo el universo
terminal/storage.py    guardado local o en GitHub
ui/                    páginas
```
