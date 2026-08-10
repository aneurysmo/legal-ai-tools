# Lex Workspace — sistema de diseño

## Dirección y sensación
"Expediente legal": papel, tinta, estructura de despacho — no la paleta SaaS azul genérica ni el semáforo pastel típico de dashboards de riesgo. La app se siente como revisar documentos físicos en un despacho, no como una app de analytics. El acento de marca es azul sobrio (no oxblood/guinda como en la primera versión — ver nota abajo), pero el fondo papel y la tipografía serif siguen dando la calidez de "expediente", no un frío look corporativo genérico.

## Paleta (tokens en `app.py`, bloque `THEME_CSS`)
- `--ink: #211d1a` — texto principal (tinta, no negro puro)
- `--ink-soft: #5b5449` — texto secundario
- `--ink-faint: #8c8477` — metadatos, etiquetas
- `--paper: #faf8f3` — fondo de página
- `--paper-deep: #f1ece1` — superficies secundarias (sidebar, tarjetas, mensajes de chat)
- `--paper-inset: #ece5d6` — inputs (más oscuro que su entorno, "recibe" contenido)
- `--rule: rgba(33,29,26,0.12)` / `--rule-soft: rgba(33,29,26,0.07)` — bordes
- `--accent: #1d3a5f` (azul sobrio empresarial) — acción primaria, énfasis, marca. **Cambiado de `#8a3324` (oxblood/guinda)** a pedido del cliente ("botones, títulos y objetos en tonos guinda" se percibían fuera de tono) — mismo azul navy que ya usaba el tema Corporativo, ahora también el acento por defecto de Clásico. `CLASICO_DARK_CSS` usa `#5487ce` (el mismo azul aclarado del Corporativo oscuro) en vez del coral `#d1694f` anterior. `.streamlit/config.toml` `primaryColor` se actualizó a juego (`#1d3a5f`), para que los pocos controles nativos que no pasan por nuestras variables (ver gotcha de `primaryColor` más abajo) no queden desentonados aunque ya estén forzados por CSS donde importa.
- `--on-accent: #ffffff` — texto sobre superficies `--accent` (botones primarios, botón/encabezado del chat flotante). Blanco a pedido del cliente (se probó gris claro primero, pero el cliente pidió volver a blanco). Un solo valor cubre las 4 combinaciones de tema porque `--accent` es siempre un azul (navy o su variante clara) en las cuatro — no necesita redefinirse por tema, a diferencia de `--accent-2`.
- Riesgo: alto `#8a3324` (oxblood/guinda, **deliberadamente sin cambiar** — es una convención semántica de alerta, no la marca; cambiarlo le quitaría la señal visual de "alto riesgo"), medio `#a6741c` (ochre), bajo `#3f6b4c` (musgo) — `RISK_COLOR` en `app.py`

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
- Toggle "🌙 Modo oscuro" en el sidebar (solo en el área de trabajo, nunca en login), controla `st.session_state["dark_mode"]`. Al activarse, se inyecta el bloque `:root` oscuro del tema activo inmediatamente después de `THEME_CSS`.
- Gotcha importante: los widgets nativos de Streamlit (`st.selectbox`, `st.date_input`, botones `kind="secondary"`) NO heredan nuestras variables `:root` automáticamente — Streamlit los pinta con su propio CSS interno (clases `st-emotion-cache-*`/React Aria) que hay que sobreescribir explícitamente por selector (`[data-testid="stSelectbox"] input`, `[data-testid="stDateInput"] input`, `button[kind="secondary"]`, etc.), fijando **tanto fondo como color de texto juntos** — fijar solo uno de los dos (p. ej. solo `color` sin `background`) puede dejar texto claro sobre fondo claro (o viceversa) en modo oscuro, aunque en claro se vea bien por coincidencia.
- Los menús desplegables (`role="listbox"`/`role="option"`) y el calendario del date picker se montan en un portal fuera del árbol de la app — necesitan su propia regla, no basta con estilizar el input.
- Antes de dar por buena una pieza de UI en modo oscuro: probarla con Playwright (no basta con mirar la vista por defecto) — los selects, date inputs y botones secundarios fallaron en la primera pasada precisamente porque solo se verificó la vista de Análisis de riesgo contractual, que no los usa.

## Matriz de temas: Clásico / Corporativo × Claro/Oscuro
Pedido por el cliente antes de una demo con abogados: el beige "expediente legal" transmite cercanía, pero un despacho asocia navy/gris/blanco con solidez institucional. En vez de reemplazar el tema, se agregó como alternativa — dos ejes independientes en `st.session_state`: `theme` (`"clasico"` | `"corporativo"`) y `dark_mode` (bool). Selector "Tema" en el sidebar (`st.sidebar.selectbox`, justo debajo del bloque de marca) + el toggle de modo oscuro existente, combinados dan 4 variantes.
- `THEME_CSS` sigue siendo la base (valores Clásico claro). Encima se inyecta como máximo UN bloque `:root` de override según la combinación: `CLASICO_DARK_CSS`, `CORPORATIVO_CLARO_CSS` o `CORPORATIVO_OSCURO_CSS`. Todo el resto del CSS no cambia — sigue leyendo los mismos nombres de variable.
- Paleta Corporativo claro: `--ink:#16202e` `--paper:#ffffff` `--paper-deep:#f3f6fa` `--paper-inset:#e8edf4` `--accent:#1d3a5f` (navy). Oscuro: `--paper:#0c131d` `--accent:#5487ce` (navy aclarado para contraste).
- **Gotcha nuevo**: `.streamlit/config.toml` fija un `primaryColor` estático (`#8a3324`, el oxblood de Clásico) que Streamlit usa para pintar controles nativos que NO pasan por nuestras variables CSS en absoluto — el punto del radio seleccionado (`[data-testid="stRadioOption"][data-selected="true"]`) y el riel del toggle activado (`label:has(input[role="switch"]:checked)`). Sus divs internos no tienen `data-testid` estable; hay que apuntar por estructura usando `div:empty` (el círculo/thumb, que no tiene hijos) y `div:has(> div:empty)` (su contenedor inmediato) para no pintar también el div hermano que envuelve el texto de la opción (mismo nivel de anidamiento, pero con contenido → nunca es `:empty`).
- Los `box-shadow` que antes usaban `rgba(33,29,26,...)` (el ink de Clásico hardcodeado) se cambiaron a `rgba(0,0,0,...)` + `var(--rule)` como anillo, para que se vean correctos en cualquiera de los 4 combos sin duplicar reglas por tema.
- **Acento secundario `--accent-2` (dorado discreto)**: pedido explícito del cliente junto con navy/blanco/gris. Se define como `var(--accent)` (no-op) en la paleta base de `THEME_CSS`, así que Clásico nunca lo usa realmente — solo `CORPORATIVO_CLARO_CSS`/`CORPORATIVO_OSCURO_CSS` lo redefinen con un dorado apagado (`#a5883f` claro / `#c2a35e` oscuro, no metálico ni brillante). Único uso hoy: `border-left` de 2px en el ítem de navegación activo del sidebar (`[data-testid="stRadioOption"][data-selected="true"]`, que en este componente de React Aria **es** el `<label>`, no un ancestro — confirmado por inspección de DOM, no asumido). Antes de sumar más usos: mantenerlo raro/puntual (indicador, no relleno) — es un acento, no un segundo color de marca.

## Marca (sidebar + login)
- `.brand` / `.brand-mark` / `.brand-name` / `.brand-tag`: insignia sólida (cuadrado `--accent` redondeado, 42px sidebar / 54px con `.brand-lg` en login) + wordmark en Source Serif 4 700 + tagline uppercase tracked en `--ink-faint`. Reemplazó un `st.sidebar.title` plano — ese patrón (título + emoji suelto) no vuelve a usarse para la marca.
- Mismo componente en sidebar (`.brand-sidebar`, con `border-bottom` separador) y en la tarjeta de login (`.brand-lg`, sin separador) — un solo lugar para tocar el logo si cambia.

## Chat flotante: una sola superficie, no boton + ventana
- El botón redondo (💬) y el panel son **estados mutuamente excluyentes**, no dos piezas flotantes simultáneas: al abrir, el botón redondo desaparece y su función de cerrar se muda al encabezado del propio panel (junto a un botón de expandir). Esto fue un pedido explícito de cliente ("se ve como ventana añadida, no integrada") — la solución fue reducir de dos superficies a una, no solo retocar sombras.
- Dos tamaños vía `st.session_state["chat_expanded"]`, cada uno con su propia `st.container(key=...)` (`floating_chat_panel_compact` 380×460px / `floating_chat_panel_expanded` ~680px×720px máx) — Streamlit envuelve cada hijo de un container en su propio `stLayoutWrapper`, así que `flex:1`/`display:flex` en el contenedor exterior **no** se propaga a los hijos reales; más simple y confiable fijar alturas explícitas (`max-height` en px) por variante que perseguir una cadena flex a través de wrappers de Streamlit.
- Encabezado (`.st-key-floating_chat_header_row`, fondo `--accent`) usa `st.columns([5,1,1])` para título + expandir + cerrar; los botones ahí dentro se fuerzan a `background:transparent` para no chocar con la regla global de `button[kind="secondary"]`.

## Calendario mensual (vista "Plazos y calendario procesal")
- Cuadrícula propia en HTML/CSS (clases `.calendario*` en `THEME_CSS`), **no** una librería de terceros tipo `streamlit-calendar`/FullCalendar — decisión explícita del cliente tras comparar pros/contras: a la escala esperada (~20 usuarios) ninguna opción es más cara en cómputo, así que la decisión fue de consistencia visual (hereda Clásico/Corporativo/oscuro gratis) y de no sumar una dependencia cuyo CSS no sigue nuestros tokens (misma fricción que ya tuvimos con `primaryColor` de Streamlit).
- Se construye con el módulo estándar `calendar` (importado como `calendar_module` en `app.py` para no chocar con la variable local `calendario` de `generar_ics` en `deadline_extractor.py`) — `Calendar(firstweekday=0).monthdatescalendar(anio, mes)` da las semanas completas, incluyendo días de meses adyacentes para rellenar la grilla, sin calcular alineación a mano.
- Mismo criterio que `.finding-card`: fondo neutro (`--paper-deep`/`--paper-inset` en días fuera de mes) + `border-left` de color semántico por evento, nunca fondos teñidos. Se evitó a propósito `color-mix()` u otras funciones CSS nuevas, por compatibilidad.
- Días con más de 3 eventos truncan a "+N más" en vez de romper el alto de la celda.
- Navegación de mes vía `st.session_state["plazos_calendario_mes"] = (anio, mes)` + dos `st.button` ("◀"/"▶") con `st.rerun()`, mismo patrón que el selector de tema.

### Siempre visible: submenú de pestañas, no gateado al final del flujo
- Pedido explícito del cliente: el calendario no debía aparecer solo hasta el final del flujo de análisis. Se resolvió con `st.tabs(["📄 Analizar documento", "📅 Calendario"])` dentro de `vista_plazos()` — la pestaña "Calendario" es alcanzable en cualquier momento, con estado vacío propio ("aún no has analizado ningún documento" / "confirma las fechas para verlas aquí") en vez de estar oculta.
- **Gotcha de `st.tabs`**: a diferencia de un router `if/elif`, Streamlit ejecuta el cuerpo de **ambas** pestañas en cada rerun (solo oculta con CSS la que no está activa). Una inicialización "una sola vez" de `plazos_calendario_mes` en la pestaña Calendario se dispara en el primer render (vacío, antes de analizar nada) y nunca vuelve a saltar al mes real tras confirmar. Solución: guardar en `st.session_state["plazos_calendario_synced_doc"]` a qué documento corresponde el último salto automático de mes, y re-saltar solo cuando `plazos_documento` cambia (documento nuevo o recién confirmado) — así no se pisa la navegación manual del usuario (◀/▶) en reruns posteriores del mismo documento.

### Un color por categoría, no dos tonos genéricos
- Pedido explícito del cliente: diferenciar cada categoría con su propio color de texto, no solo gris-para-fechas/azul-para-plazos. `CATEGORIA_COLOR` (en `deadline_extractor.py`) mapea cada una de las 7 categorías a una variable CSS (`--cat-notificacion`, `--cat-contestar`, `--cat-audiencia`, `--cat-pruebas`, `--cat-sentencia`, `--cat-impugnar`, `--cat-otra`), definidas en `THEME_CSS` (valores para fondo claro) y re-aclaradas en `CLASICO_DARK_CSS`/`CORPORATIVO_OSCURO_CSS` (mismo patrón que `--accent`/`--accent-2`) para legibilidad sobre fondo oscuro.
- Se usa como **color de texto** de la píldora en el calendario (no solo como borde) y como `--finding-color` de las tarjetas de detalle — mismo mapeo en ambos componentes, para que se lean como el mismo sistema.
- La etiqueta de cada píldora incluye el nombre del caso (`{categoria} · {nombre_caso}`, mismo dato que ya usa `generar_ics` para nombrar sus eventos), para relacionar la fecha con el documento del que proviene, no solo mostrar la categoría genérica. Se trunca visualmente con `text-overflow: ellipsis`; el texto completo queda disponible vía atributo `title` (tooltip nativo al pasar el mouse).

## Línea de tiempo del caso (case_timeline.py + vista_timeline())
- Mismo patrón de "pestañas siempre visibles" que "Plazos y calendario procesal": `st.tabs(["📂 Documentos", "🕒 Línea de tiempo"])`, la segunda con estado vacío propio antes de analizar. A diferencia de `vista_plazos`, aquí las tarjetas de eventos/inconsistencias, el gráfico PNG y los botones de descarga viven todos en la pestaña "Línea de tiempo" (no en "Documentos") — con múltiples documentos y potencialmente muchos eventos, tiene más sentido que "Documentos" se quede solo con el flujo de carga y un resumen corto, y que el resultado completo viva en un solo lugar.
- **Multi-archivo con nombre original preservado**: `st.file_uploader(..., accept_multiple_files=True)`. El helper compartido `save_uploaded_file()` (usado por las demás vistas) crea el archivo temporal con un nombre aleatorio — no importa en esas vistas, pero aquí el nombre de archivo original SÍ es un dato del resultado (`fuente` de cada evento). Se creó un temporal propio por archivo, cada uno en su propio directorio (`tempfile.mkdtemp()`), preservando el nombre original (`tmp_dir / uploaded_file.name`) — de lo contrario el reporte mostraba nombres tipo `tmpexjpd1wz.docx` en vez de `contrato.docx`.
- **Años ambiguos sin widget por evento**: a diferencia de `vista_plazos` (pocas fechas, un documento), aquí puede haber muchos eventos en varios documentos — un `st.number_input` por fecha ambigua sería inmanejable. Se resuelve en modo no interactivo (año actual, igual que `--no-interactivo` en la CLI) y se avisa con un `st.warning` cuáles fechas se asumieron y con qué año, para que el usuario las revise manualmente si hace falta.
- **Generación de artefactos una sola vez**: el PNG/MD/PPTX/HTML/JSON se generan justo después de analizar y se guardan como bytes en `session_state` — no se regeneran en cada rerun (ej. al hacer clic en un botón de descarga, que ya de por sí dispara un rerun de Streamlit). Mismo criterio que el `.ics`/reporte de `vista_plazos`.
- **Gráfico matplotlib (`generar_grafico_png`)**: la fecha y la descripción de cada evento se combinan en una sola etiqueta del eje Y (`ax.set_yticklabels`), en vez de dibujar dos columnas de texto a mano en posiciones fijas. Un primer intento posicionaba la fecha con un offset fijo en coordenadas de datos junto a la barra — se veía bien con rangos de fechas cortos, pero en cuanto el rango se ampliaba (ej. por una fecha sin año resuelta al año actual, muy lejos del resto) la fecha terminaba renderizada casi encima de la etiqueta del evento. Un segundo intento con dos columnas de texto en fracción-de-ejes (`ax.get_yaxis_transform()`, anclaje por la derecha) tampoco funcionó: una descripción larga anclada a la derecha crece hacia la izquierda sin límite y se come el hueco reservado para la fecha. La solución robusta fue no pelear con posicionamiento manual: dejar que matplotlib mida el ancho real de la etiqueta combinada (como ya hace por defecto con `set_yticklabels`), que es exactamente para lo que está diseñado y no depende de ningún rango de fechas ni longitud de texto asumida.
