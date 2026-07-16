# Legal AI Tools — sistema de diseño

## Dirección y sensación
"Expediente legal": papel, tinta, sellos de lacre — no la paleta SaaS azul genérica ni el semáforo pastel típico de dashboards de riesgo. La app se siente como revisar documentos físicos en un despacho, no como una app de analytics.

## Paleta (tokens en `app.py`, bloque `THEME_CSS`)
- `--ink: #211d1a` — texto principal (tinta, no negro puro)
- `--ink-soft: #5b5449` — texto secundario
- `--ink-faint: #8c8477` — metadatos, etiquetas
- `--paper: #faf8f3` — fondo de página
- `--paper-deep: #f1ece1` — superficies secundarias (sidebar, tarjetas, mensajes de chat)
- `--paper-inset: #ece5d6` — inputs (más oscuro que su entorno, "recibe" contenido)
- `--rule: rgba(33,29,26,0.12)` / `--rule-soft: rgba(33,29,26,0.07)` — bordes
- `--accent: #8a3324` (oxblood/lacre) — acción primaria, énfasis
- Riesgo: alto `#8a3324`, medio `#a6741c` (ochre), bajo `#3f6b4c` (musgo) — `RISK_COLOR` en `app.py`

## Tipografía
- **Source Serif 4** (500/600/700) — títulos, valores destacados (`h1-h3`, `.expediente-title`, `.risk-metric-value`, `.finding-tag`)
- **Inter** (400/500/600) — todo el resto de la UI
- Google Fonts vía `@import` en `THEME_CSS`

## Profundidad — elegido: bordes sutiles + superficie plana (sin sombras)
- Un solo hue (ink), solo cambia la luminosidad entre superficies
- Bordes `rgba` de baja opacidad, nunca hex sólido
- Tarjetas: `border-left` de 3-4px con el color semántico como acento (no relleno de color completo tipo "semáforo")

## Patrones de componentes reutilizables
- `.expediente-card` — tarjeta centrada de login/registro (padding 2rem/2.25rem, radius 10px, sombra whisper `0 1px 2px + 0 4px 16px`)
- `.finding-card` — ficha de "anotación al margen": `border-left` con color semántico, tag en serif, cita en itálica, texto secundario en `--ink-soft`. Reutilizada tanto para hallazgos de riesgo como para ítems de la biblioteca de documentos (con `--finding-color: var(--ink-faint)` quand neutral)
- `.risk-metric` — tarjeta de métrica con acento superior de 3px, valor en serif con `tabular-nums`
- `.grounding-badge` — pill pequeña (uppercase, tracked, 0.7rem) que indica si una respuesta del chat está anclada en un documento (`--accent` border) o es conocimiento general (`--ink-faint`)
- `[data-testid="stAlertContainer"]` — barra de acento izquierda por tipo semántico en vez de relleno de color sólido
- `[data-testid="stChatMessage"]` — burbujas en `--paper-deep` con borde sutil, sin colores de fantasía por rol
- Botones primarios (`type="primary"`) — color `--accent`, `scale(0.97)` en `:active`

## Densidad / espaciado
- Base 4px, paddings de tarjetas en 8-16px (contenido denso tipo herramienta de trabajo, no brochure)
- Padding simétrico salvo asimetría deliberada (ej. `.expediente-title` con más espacio abajo antes de la línea divisoria)

## Notas de uso
- Todo contenido generado por el LLM que se inserta vía `unsafe_allow_html=True` debe pasar por `html.escape()` primero (ver `vista_riesgo_contractual` y el panel de biblioteca en `vista_investigacion`).
- Antes de agregar una nueva pieza de UI: revisar si `.finding-card`/`.risk-metric`/`.grounding-badge` ya cubren el caso antes de crear una clase nueva.

## Modo oscuro
- Toggle "🌙 Modo oscuro" en el sidebar (solo en el área de trabajo, nunca en login), controla `st.session_state["dark_mode"]`. Al activarse, se inyecta `DARK_MODE_CSS` (bloque `:root` con los mismos nombres de token, valores invertidos) inmediatamente después de `THEME_CSS`.
- Gotcha importante: los widgets nativos de Streamlit (`st.selectbox`, `st.date_input`, botones `kind="secondary"`) NO heredan nuestras variables `:root` automáticamente — Streamlit los pinta con su propio CSS interno (clases `st-emotion-cache-*`/React Aria) que hay que sobreescribir explícitamente por selector (`[data-testid="stSelectbox"] input`, `[data-testid="stDateInput"] input`, `button[kind="secondary"]`, etc.), fijando **tanto fondo como color de texto juntos** — fijar solo uno de los dos (p. ej. solo `color` sin `background`) puede dejar texto claro sobre fondo claro (o viceversa) en modo oscuro, aunque en claro se vea bien por coincidencia.
- Los menús desplegables (`role="listbox"`/`role="option"`) y el calendario del date picker se montan en un portal fuera del árbol de la app — necesitan su propia regla, no basta con estilizar el input.
- Antes de dar por buena una pieza de UI en modo oscuro: probarla con Playwright (no basta con mirar la vista por defecto) — los selects, date inputs y botones secundarios fallaron en la primera pasada precisamente porque solo se verificó la vista de Análisis de riesgo contractual, que no los usa.
