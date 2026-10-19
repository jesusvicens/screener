# Terminal de análisis de empresas

Terminal personal para analizar cotizadas de EE. UU. con tu propio modelo (el Excel de Adobe convertido en motor de cálculo).

- **Datos de ~10.000 empresas** desde la API gratuita de la SEC (EDGAR/XBRL): PyG, balance y cash flow anuales de los 10-K, hasta 15 años.
- **Precios** de Yahoo Finance (con Stooq de respaldo). Si fallan, escribes el precio a mano.
- **Tu análisis se calcula al abrir cada empresa**: no hay nada precalculado. Si quieres pasarlo por muchas a la vez, está la página *Lote*.
- **Coste cero**: sin API de Claude ni suscripciones de datos.

## Qué hay dentro

| Página | Qué hace |
|---|---|
| **Empresa** | Ficha con tus hojas: Histórico estilo macrotrends (precio, ingresos y beneficio, activos y pasivos, márgenes, ratios de precio diarios, otros ratios y métricas), Examen (43 preguntas, misma puntuación), Estados financieros, Modelo EPS (+ tu modelo de Buffettología), ROIC (+ I+D capitalizado), Escenarios y valoración (fase, 4 escenarios, proyección a 10 años, test de cobertura, margen de seguridad, ventana de horizontes, test de exposición), presentaciones en la SEC y notas. Botón para guardar y exportar a Excel. |
| **Ficha: navegación** | Cuatro secciones arriba (Datos · Análisis · Valoración · Propiedad y fuentes) y sus pestañas debajo. Cabecera con mini-gráficos (precio 1 año, PER frente a su mediana, ventas), cifras en formato español. |
| **Segmentos** (ficha) | Ventas por negocio, producto y geografía de los últimos 10-K (XBRL dimensional): evolución, peso, crecimiento y margen por segmento si lo publican. |
| **Comparables** (ficha) | Competidores propuestos (misma industria y tamaño) y editables; puesto de la empresa en cada métrica, tabla con la mediana del grupo y gráficos. |
| **Bandas y sensibilidad** (ficha) | BPA normalizado; percentiles históricos de PER y P/FCF con su precio equivalente y gráfico de bandas; tabla de rentabilidad anual por crecimiento del BPA × PER de salida (con dividendos). |
| **Directivos y fondos** (ficha) | Compras y ventas de directivos (formularios 4, últimos 2 años, con planes 10b5-1) sobre la cotización, y superinversores que la tienen según sus 13F (24 fondos: Berkshire, Akre, Fundsmith, Markel, Oaktree, Himalaya, TCI…) con su peso y el cambio del trimestre. |
| **SEC y Notas** (ficha) | Buscador de texto completo en todos sus documentos de la SEC (menciones por informe anual y fragmentos). Bitácora con fecha (tesis, resultados, compras, ventas…). |
| **Histórico** (ficha) | Además de anual: vista trimestral y últimos 12 meses, y la categoría «Dividendos y recompras» (retorno al accionista frente al FCF). |
| **Riesgo** (pestaña de la ficha) | Tu método «Parte II · El riesgo»: BPA y precio de salida a 5 y 10 años, distribución de valores futuros, test de cobertura con probabilidades de prueba (cola izquierda engordada), ventana de horizontes, valor estimado y tabla de precios de compra, test de exposición por perfil de inversor (editable), preguntas de supervivencia y conclusión redactada. |
| **Screener** | Estilo macrotrends sobre **todas** las cotizadas (~5.300 con datos): 51 métricas (crecimientos de ventas, BPA, beneficio, FCF y patrimonio a 1/3/5 años, crecimiento medio anual con los años que elijas (2-10), consistencia, márgenes, ROE/ROA/ROIC, salud, política de capital y valoración: PER, PEG, P/Ventas, P/VC, P/FCF, EV/EBIT, EV/EBITDA, rentabilidades). Filtros con mínimo y máximo por cualquier métrica, sector, industria, mercado y búsqueda; plantillas (Fisher/Munger, crecimiento de BPA, compounders baratos…) y las tuyas propias; columnas y orden a elegir; CSV; enviar a la ficha o al lote. Fundamentales de la SEC (≈1-2 min, caché semanal); precios, capitalización y sector del screener público de Nasdaq (una llamada, caché diaria). |
| **Lote** | Pasa el modelo completo por una lista de tickers (o por el resultado del screener) y ordena por margen de seguridad. |
| **Cartera** | Tus movimientos (compras, ventas, dividendos, splits) a mano o importados del extracto CSV de Interactive Brokers; posiciones con valor actual en divisa y en euros, plusvalía latente y enlace a tu valoración; pestaña IRPF con las transmisiones por FIFO en euros (tipo de cambio del BCE de cada fecha), aviso de la regla de los dos meses, dividendos con retención en origen y Excel para la declaración. |
| **Mis análisis** | Las empresas que has guardado, con su nota y su valoración del día en que guardaste. |
| **Panel, prioridad y listas** (pestaña del Screener) | **Panel** con tus listas y tu cartera (precio, variaciones, distancia al objetivo, próximos resultados y avisos) y **calendario de resultados** por semanas (fecha estimada con el patrón de cada empresa). Qué analizar primero: empresas con mejor nota financiera que aún no has mirado, ordenadas por prioridad (70 % nota + 30 % precio relativo por rentabilidad FCF). Y tus listas de seguimiento (A analizar, Analizadas, Para más adelante, Caras, Descartadas y las tuyas; una empresa puede estar en varias) con comentario, precio objetivo y aviso cuando llega a ese precio. Se añaden empresas desde aquí, desde la ficha o desde el screener. |

### Cómo funciona el examen
- Bloques cualitativos (Operativo, Producto, Dirección, Estrategia, Valores, Sector): los contestas tú. En la pestaña hay un texto listo para pegar en tu chat de Claude y trabajarlos ahí.
- Bloques financieros (PyG, Balance, Cash Flow y Asignación de capital, 21 preguntas con criterios de Buffett y 10 años de datos): la terminal **propone** la respuesta y te enseña el cálculo; tú la cambias si no estás de acuerdo. «No aplica» no cuenta en la media (bancos, aseguradoras, datos que no existen). Las reglas están en `terminal/exam.py` (función `suggestions`).

### Escenarios
Las casillas vacías usan la propuesta por fase de tu Excel (la ves en gris). Escribes encima para fijar tu supuesto y la borras para volver a la propuesta. El escenario **Desastre**, que en el Excel daba `#REF!`, aquí se calcula.

## Excel con tu plantilla
El botón «⬇ Excel (mi plantilla)» de cada ficha genera tu propio Excel de análisis (`templates/plantilla_analisis.xlsx`, con todas sus fórmulas) relleno con los datos de la empresa, tus supuestos, la parte de riesgo y el examen nuevo (4 bloques financieros con desplegables y el dato que justifica cada propuesta en la columna I). Excel recalcula al abrir.

## Notas financieras de todas las empresas
`scripts/notas_financieras.py` calcula el examen financiero de todo el universo con el archivo masivo de la SEC (`companyfacts.zip`). Lo ejecuta cada domingo la GitHub Action «Notas financieras» y guarda `data/notas_financieras.csv.gz`; el screener lo lee. Para lanzarlo a mano: GitHub → Actions → «Notas financieras (todas las empresas)» → Run workflow.

## Cualitativo y documentos (OneDrive)
La pestaña «Cualitativo y documentos» de cada ficha reúne tu examen cualitativo (respuestas y motivos por bloque), un **dossier** en texto
(lo que has estudiado de la empresa; lo escribes tú o me lo pides en el chat) y los **documentos de su carpeta en tu OneDrive**, con
vista previa. La conexión con OneDrive es de solo lectura (Microsoft Graph, permiso Files.Read); se configura una vez con
`ONEDRIVE_CLIENT_ID` en los Secrets (pasos en `terminal/onedrive.py`) y el botón «Conectar OneDrive».

## Guías y resultados
Pestaña de la ficha con la guía que da la dirección cada trimestre frente al resultado real, la evolución de la guía anual
(primera guía, subidas, bajadas), el resumen y el tono de cada presentación de resultados, la nota de prensa de la SEC y la
transcripción guardada en tu OneDrive. Las guías se extraen de las notas de prensa (8-K) y se guardan con el análisis
(«guias»); los resultados trimestrales reales salen del XBRL de la SEC para cualquier empresa (`terminal/trimestres.py`).

## Datos preparados cada noche
Para que la app abra rápido aunque Streamlit la haya reiniciado (su disco se borra al dormirse):
- **Screener** (datos públicos): la GitHub Action «Datos del screener» publica cada noche, de lunes a viernes, precios y sectores (cada día) y fundamentales (cada semana) en la rama `datos` de este repo. La app los lee al arrancar.
- **Superinversores (13F)**: la misma Action prepara cada semana las carteras de los 24 fondos seguidos (`superinversores.parquet`).
- **Fichas de tus empresas** (analizadas, en listas o en cartera): la Action «Fichas de mis empresas» de tu repo privado de datos guarda cada noche sus datos de la SEC y su cotización en la rama `fichas`. La ficha los lee con tu `GITHUB_TOKEN`; si una empresa no está ahí (o el dato tiene más de 36 h), la descarga de la SEC/Yahoo como siempre.
Las dos ramas se reescriben cada noche sin historial, así que no engordan los repos.

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
terminal/trimestres.py trimestres y últimos 12 meses (XBRL 10-Q/10-K)
terminal/segmentos.py  ventas por segmento, producto y geografía (XBRL dimensional)
terminal/comparables.py, bandas.py   comparables; bandas de PER/PFCF, BPA normalizado y sensibilidad
terminal/insiders.py, superinversores.py   formularios 4 y carteras 13F
terminal/calendario.py, busqueda.py    fechas de resultados; búsqueda de texto completo en la SEC
ui/                    páginas
```
