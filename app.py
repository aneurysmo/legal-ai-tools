"""
app.py

Interfaz unificada en Streamlit para las herramientas de IA legal del
proyecto:

  1. Analizador de riesgo contractual (contract_risk_analyzer.py)
  2. Investigacion juridica / Q&A sobre PDF (legal_research.py)

Esta app NO reimplementa la logica de analisis: reutiliza directamente las
funciones ya existentes en ambos modulos (extraccion de texto, chunking,
llamadas al LLM, construccion de prompts/reportes, etc.).

Uso:
    streamlit run app.py
"""

import calendar as calendar_module
import html
import io
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

import auth
import case_timeline
import config
import document_drafting
import knowledge_base
import legal_research
from contract_risk_analyzer import (
    build_analysis_prompt,
    build_report,
    chunk_text as chunk_text_contract,
    dedupe_findings,
    extract_text,
    parse_llm_json,
    RISK_EMOJI,
    RISK_LABEL,
)
from deadline_extractor import (
    calcular_plazos,
    cargar_festivos,
    CATEGORIA_COLOR,
    CATEGORIA_EMOJI,
    CATEGORIAS,
    extraer_fechas_y_plazos,
    fecha_notificacion_principal,
    generar_ics,
    generar_reporte_markdown,
    normalizar_fecha,
)
from deadline_extractor import extract_text as extract_text_plazos
from legal_research import (
    ask_llm,
    build_prompt,
    chunk_text as chunk_text_research,
    embed_chunks,
    extract_text_from_pdf,
)

st.set_page_config(page_title="Lex Workspace", page_icon="⚖️", layout="wide")


# ---------------------------------------------------------------------------
# Tema visual — "expediente legal": papel, tinta, sellos de lacre.
# Se inyecta una sola vez via CSS; los tokens de color viven aqui para que
# el resto de la app (tabla de hallazgos, tarjetas, alertas) los reutilice.
# ---------------------------------------------------------------------------

RISK_COLOR = {"alto": "#8a3324", "medio": "#a6741c", "bajo": "#3f6b4c"}

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

:root {
  --ink: #211d1a;
  --ink-soft: #5b5449;
  --ink-faint: #8c8477;
  --paper: #faf8f3;
  --paper-deep: #f1ece1;
  --paper-inset: #ece5d6;
  --rule: rgba(33,29,26,0.12);
  --rule-soft: rgba(33,29,26,0.07);
  --accent: #1d3a5f;
  --accent-soft: rgba(29,58,95,0.08);
  /* Texto sobre superficies de --accent (botones primarios, boton/encabezado
     del chat flotante): blanco, por pedido del cliente. Un solo valor sirve
     para las 4 combinaciones de tema porque --accent es siempre un azul
     (navy o su variante clara) en las cuatro -- no hace falta redefinirlo
     por tema. */
  --on-accent: #ffffff;
  /* Acento secundario: no existe en Clasico, asi que por defecto es igual
     al acento primario (no-op). Solo el tema Corporativo lo redefine con un
     dorado discreto -- ver CORPORATIVO_CLARO_CSS / CORPORATIVO_OSCURO_CSS. */
  --accent-2: var(--accent);
  /* Un color por categoria procesal (calendario + tarjetas de "Plazos y
     calendario procesal"), para diferenciarlas de un vistazo. Valores para
     fondo claro (Clasico claro y Corporativo claro, que no los redefine);
     CLASICO_DARK_CSS y CORPORATIVO_OSCURO_CSS los aclaran para legibilidad
     sobre fondo oscuro. */
  --cat-notificacion: #2f6f76;
  --cat-contestar: #8a3324;
  --cat-audiencia: #1d3a5f;
  --cat-pruebas: #6b4fa0;
  --cat-sentencia: #a6741c;
  --cat-impugnar: #b23b6b;
  --cat-otra: #5b5449;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
h1, h2, h3, [data-testid="stMetricValue"] {
  font-family: 'Source Serif 4', serif !important;
  letter-spacing: -0.01em;
}
h1 { font-weight: 600; }

[data-testid="stAppViewContainer"] { background: var(--paper); color: var(--ink); }

/* Los encabezados y botones secundarios de Streamlit traen su propio color
   de texto pensado para fondo claro; en modo oscuro se lo forzamos al token
   del tema para que no queden ilegibles sobre el fondo oscuro. */
h1, h2, h3, h4, [data-testid="stHeading"] * {
  color: var(--ink) !important;
}
button[kind="secondary"], button[kind="secondaryFormSubmit"] {
  background: var(--paper-inset) !important;
  color: var(--ink) !important;
  border-color: var(--rule) !important;
}

[data-testid="stSidebar"] {
  background: var(--paper-deep);
  border-right: 1px solid var(--rule);
  color: var(--ink);
}
[data-testid="stSidebar"] hr { border-color: var(--rule-soft); margin: 0.9rem 0; }

/* Marca: una insignia solida + wordmark en serif, no un st.title generico.
   El mismo componente se reusa (con .brand-lg) en la tarjeta de login para
   que la marca tenga presencia consistente en toda la app. */
.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.brand-sidebar {
  padding-bottom: 1.05rem;
  margin-bottom: 0.85rem;
  border-bottom: 1px solid var(--rule);
}
.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
  flex-shrink: 0;
}
.brand-name {
  font-family: 'Source Serif 4', serif;
  font-weight: 700;
  font-size: 1.28rem;
  letter-spacing: -0.01em;
  color: var(--ink);
  line-height: 1.15;
}
.brand-tag {
  font-size: 0.66rem;
  font-weight: 500;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-top: 0.15rem;
  white-space: nowrap;
}
.brand-lg .brand-mark { width: 54px; height: 54px; font-size: 1.6rem; border-radius: 12px; }
.brand-lg .brand-name { font-size: 1.6rem; }

/* Radio nav en el sidebar: lista tipo carpeta, no burbujas genericas */
[data-testid="stSidebar"] [role="radiogroup"] {
  gap: 0.15rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
  transition: background-color 120ms ease-out;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: var(--paper-inset);
}
/* El punto del radio seleccionado viene coloreado con el primaryColor fijo
   de .streamlit/config.toml (no sigue nuestras variables de tema); se
   fuerza aqui para que respete el tema activo (Clasico/Corporativo). Se
   apunta solo a los divs "vacios" (el circulo no tiene contenido) para no
   pintar tambien el contenedor del texto de la opcion, que es un hermano
   a la misma profundidad. */
[data-testid="stRadioOption"][data-selected="true"] div:empty,
[data-testid="stRadioOption"][data-selected="true"] div:has(> div:empty) {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}
/* Indicador de seccion activa: en Clasico --accent-2 es igual a --accent
   (no-op, mismo oxblood de siempre); en Corporativo se convierte en el
   dorado discreto pedido por el cliente, como unico toque de acento fuera
   de navy/blanco/gris. */
[data-testid="stRadioOption"][data-selected="true"] {
  border-left: 2px solid var(--accent-2);
  padding-left: calc(0.6rem - 2px);
}
/* Misma correccion para el riel del toggle "Modo oscuro" cuando esta
   activado (el circulo interior ya es neutro y no necesita cambiar). */
[data-testid="stSidebar"] label:has(input[role="switch"]:checked) div:has(> div:empty) {
  background: var(--accent) !important;
}

/* Inputs: relleno ligeramente mas oscuro que el entorno (inset) */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stChatInput"] textarea {
  background: var(--paper-inset) !important;
  border: 1px solid var(--rule) !important;
  color: var(--ink) !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}

/* Selects y date pickers: Streamlit los pinta con clases internas propias
   que no siguen la cascada normal de nuestras variables, asi que hay que
   forzarlas por selector explicito (igual criterio que los text inputs de
   arriba: relleno inset, borde sutil, texto legible). Sus menus/calendarios
   se montan en un portal fuera del arbol de la app, por eso van aparte. */
[data-testid="stSelectbox"] input,
[data-testid="stMultiSelect"] input,
[data-testid="stDateInput"] input {
  background: var(--paper-inset) !important;
  border-color: var(--rule) !important;
  color: var(--ink) !important;
}
[data-testid="stSelectbox"] button,
[data-testid="stMultiSelect"] button,
[data-testid="stDateInput"] button {
  background: var(--paper-inset) !important;
  border-color: var(--rule) !important;
}
[data-testid="stSelectbox"] svg,
[data-testid="stMultiSelect"] svg,
[data-testid="stDateInput"] svg {
  fill: var(--ink-faint) !important;
}
[data-testid="stDateInput"] input::placeholder {
  color: var(--ink-faint) !important;
  opacity: 1;
}
[data-testid="stDateInput"] div:has(> svg[title="Clear value"]) {
  background: var(--paper-inset) !important;
}

/* El listbox de opciones y el calendario se montan en un portal fuera del
   arbol de la app (top-layer), por eso necesitan su propia regla. */
[role="listbox"], [role="option"] {
  background: var(--paper-deep) !important;
  color: var(--ink) !important;
  border-color: var(--rule) !important;
}
[role="option"][aria-selected="true"], [role="option"]:hover {
  background: var(--paper-inset) !important;
}

/* Botones primarios: sello de lacre, no azul SaaS */
button[kind="primary"], button[kind="primaryFormSubmit"] {
  background: var(--accent) !important;
  color: var(--on-accent) !important;
  border: none !important;
  font-weight: 500;
  transition: transform 100ms ease-out;
}
/* La etiqueta del boton se renderiza como stMarkdownContainer > p, y la
   regla global de parrafos (mas abajo, "[data-testid=stMarkdownContainer] p")
   la pinta con --ink con !important -- gana por especificidad de selector
   aunque el boton ya fije su propio color. Se fuerza aqui explicitamente
   para que el texto del boton primario siga --on-accent, no --ink. */
button[kind="primary"] [data-testid="stMarkdownContainer"] p,
button[kind="primaryFormSubmit"] [data-testid="stMarkdownContainer"] p {
  color: var(--on-accent) !important;
}
button[kind="primary"]:active, button[kind="primaryFormSubmit"]:active { transform: scale(0.97); }

/* Alertas: barra de acento a la izquierda en vez de relleno solido */
[data-testid="stAlertContainer"] {
  background: var(--paper) !important;
  border: 1px solid var(--rule) !important;
  border-left-width: 3px !important;
  border-radius: 6px;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
  border-left-color: #3f6b4c !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
  border-left-color: var(--accent) !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
  border-left-color: #a6741c !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
  border-left-color: var(--ink-faint) !important;
}
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] strong {
  color: var(--ink) !important;
}

/* El formulario nativo no debe dibujar su propia caja dentro de la
   tarjeta de expediente: una sola superficie, no cajas anidadas. */
[data-testid="stForm"] {
  border: none !important;
  padding: 0 !important;
}

/* Texto de labels y pestañas: tinta del tema, no el azul-gris de Streamlit */
[data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"] p {
  color: var(--ink) !important;
}
button[data-baseweb="tab"] {
  color: var(--ink-faint) !important;
  font-weight: 500;
}
button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--accent) !important;
}
[data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }

/* Tarjeta de login/registro */
.expediente-card {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 2rem 2.25rem 1.5rem;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.05);
}
.expediente-subtitle {
  color: var(--ink-faint);
  font-size: 0.85rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 1.1rem;
  margin-bottom: 1.1rem;
}

/* Metricas de riesgo */
.risk-metric {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-top: 3px solid var(--risk-color, var(--accent));
  border-radius: 8px;
  padding: 0.85rem 1rem;
}
.risk-metric .risk-metric-label {
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.risk-metric .risk-metric-value {
  font-family: 'Source Serif 4', serif;
  font-size: 1.9rem;
  font-weight: 600;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

/* Ficha de hallazgo — anotacion al margen, no fila de tabla semaforo */
.finding-card {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-left: 4px solid var(--finding-color, var(--accent));
  border-radius: 6px;
  padding: 0.85rem 1.1rem;
  margin-bottom: 0.6rem;
}
.finding-head {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  margin-bottom: 0.35rem;
}
.finding-tag {
  font-family: 'Source Serif 4', serif;
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--ink);
}
.finding-level {
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--finding-color, var(--accent));
}
.finding-quote {
  font-style: italic;
  color: var(--ink-soft);
  font-size: 0.88rem;
  border-left: 2px solid var(--rule);
  padding-left: 0.6rem;
  margin: 0.4rem 0;
}
.finding-reco {
  color: var(--ink-soft);
  font-size: 0.88rem;
}

/* Calendario mensual (vista "Plazos y calendario procesal"): cuadricula
   propia con nuestros tokens, no un widget de terceros -- mismo criterio
   que .finding-card (fondo neutro + acento de color solo en el borde). */
.calendario {
  border: 1px solid var(--rule);
  border-radius: 10px;
  overflow: hidden;
  margin: 0.75rem 0 1.25rem;
}
.calendario-semana {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}
.calendario-encabezado {
  background: var(--paper-deep);
  border-bottom: 1px solid var(--rule);
}
.calendario-dia-nombre {
  padding: 0.4rem 0.3rem;
  text-align: center;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.calendario-dia {
  min-height: 84px;
  padding: 0.35rem;
  border-right: 1px solid var(--rule-soft);
  border-bottom: 1px solid var(--rule-soft);
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.calendario-semana .calendario-dia:last-child { border-right: none; }
.calendario-semana:last-child .calendario-dia { border-bottom: none; }
.calendario-dia-num {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--ink-soft);
}
.calendario-dia-otro-mes { background: var(--paper-inset); }
.calendario-dia-otro-mes .calendario-dia-num { color: var(--ink-faint); opacity: 0.6; }
.calendario-dia-hoy .calendario-dia-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--on-accent);
}
.calendario-evento {
  font-size: 0.66rem;
  font-weight: 600;
  line-height: 1.25;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--paper-deep);
  border-left: 2px solid var(--evento-color, var(--accent));
  color: var(--evento-color, var(--accent));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.calendario-evento-mas {
  font-size: 0.66rem;
  color: var(--ink-faint);
  padding: 0 0.35rem;
}

/* Chat de la biblioteca: burbujas silenciosas, sin colores de fantasia */
[data-testid="stChatMessage"] {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 8px;
}

/* Insignia sobre la respuesta del asistente: aclara si esta anclada en un
   documento real de la biblioteca o si es conocimiento juridico general,
   sin tener que leer el texto completo para saberlo. */
.grounding-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  margin-bottom: 0.5rem;
  background: var(--paper-inset);
  border: 1px solid var(--rule);
  color: var(--ink-faint);
}
.grounding-badge.grounded {
  color: var(--accent);
  border-color: var(--accent);
}

/* Chat flotante: disponible en cualquier vista, esquina inferior derecha.
   Antes vivia como dos piezas sueltas (boton redondo + panel aparte); ahora
   son estados mutuamente excluyentes de UNA sola superficie -- al abrir el
   panel el boton redondo desaparece y su lugar lo toma el boton de cerrar
   dentro del propio encabezado, para que se lea como un unico componente
   anclado, no como una ventana añadida encima de la pagina. El boton de
   expandir (⤢/⤡) permite crecer el panel para consultas largas. */
.st-key-floating_chat_toggle {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: fit-content;
  z-index: 999990;
}
.st-key-floating_chat_toggle button {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--accent) !important;
  color: var(--on-accent) !important;
  font-size: 1.4rem;
  box-shadow: 0 6px 20px rgba(0,0,0,0.25);
  border: none !important;
}

.st-key-floating_chat_panel_compact,
.st-key-floating_chat_panel_expanded {
  position: fixed;
  right: 24px;
  z-index: 999990;
  max-width: calc(100vw - 48px);
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.22), 0 0 0 1px var(--rule);
  overflow: hidden;
}
.st-key-floating_chat_panel_compact {
  bottom: 24px;
  width: 380px;
  height: 460px;
}
.st-key-floating_chat_panel_expanded {
  bottom: 24px;
  width: min(680px, 92vw);
  height: min(720px, calc(100vh - 48px));
}

.st-key-floating_chat_header_row {
  background: var(--accent);
  display: flex;
  align-items: center;
  padding: 0.45rem 0.5rem 0.45rem 1.1rem;
}
.st-key-floating_chat_header_row [data-testid="stHorizontalBlock"] {
  align-items: center;
  width: 100%;
}
.st-key-floating_chat_header_row [data-testid="stColumn"] {
  padding: 0 !important;
}
.floating-chat-title {
  color: var(--on-accent);
  font-family: 'Source Serif 4', serif;
  font-weight: 600;
  font-size: 1rem;
}
.st-key-floating_chat_header_row button {
  background: transparent !important;
  border: none !important;
  color: var(--on-accent) !important;
  font-size: 0.95rem;
  padding: 0.25rem 0.5rem !important;
  box-shadow: none !important;
  min-height: 0 !important;
}
.st-key-floating_chat_header_row button:hover {
  background: rgba(255,255,255,0.16) !important;
}

.floating-chat-messages {
  overflow-y: auto;
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  scrollbar-width: thin;
  scrollbar-color: var(--ink-faint) transparent;
}
.st-key-floating_chat_panel_compact .floating-chat-messages {
  max-height: 260px;
}
.st-key-floating_chat_panel_expanded .floating-chat-messages {
  max-height: 560px;
}
.floating-chat-messages:has(> .chat-bubble-empty:only-child) {
  justify-content: center;
}
.floating-chat-messages::-webkit-scrollbar { width: 8px; }
.floating-chat-messages::-webkit-scrollbar-thumb {
  background: var(--ink-faint);
  border-radius: 8px;
}

.chat-bubble {
  border-radius: 10px;
  padding: 0.5rem 0.7rem;
  font-size: 0.85rem;
  line-height: 1.45;
  max-width: 88%;
}
.chat-bubble-user {
  align-self: flex-end;
  background: var(--paper-inset);
  border: 1px solid var(--rule);
  color: var(--ink);
}
.chat-bubble-assistant {
  align-self: flex-start;
  background: var(--paper);
  border: 1px solid var(--rule);
  color: var(--ink);
}
.chat-bubble-empty {
  color: var(--ink-faint);
  font-size: 0.85rem;
  text-align: center;
  padding: 1rem 0;
}

.st-key-floating_chat_panel_compact [data-testid="stForm"],
.st-key-floating_chat_panel_expanded [data-testid="stForm"] {
  border: none !important;
  border-top: 1px solid var(--rule) !important;
  padding: 0.6rem 0.8rem !important;
  border-radius: 0 !important;
}

/* Vista previa del borrador de redaccion: se lee como un documento, no
   como un textarea de formulario generico. */
.draft-preview {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 1.5rem 1.75rem;
  max-height: 520px;
  overflow-y: auto;
  font-family: 'Source Serif 4', serif;
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
}
</style>
"""

# Cada variante de tema solo redefine los valores de los tokens (--ink,
# --paper, --accent, etc.) -- todo el resto del CSS de arriba ya los
# referencia via var(), asi que no hace falta duplicar ninguna regla por
# tema. Dos temas (Clasico / Corporativo) x dos variantes (claro/oscuro).

CLASICO_DARK_CSS = """
<style>
:root {
  --ink: #ece7dc;
  --ink-soft: #c9c2b4;
  --ink-faint: #948c7c;
  --paper: #1b1815;
  --paper-deep: #24201c;
  --paper-inset: #2e2921;
  --rule: rgba(236,231,220,0.14);
  --rule-soft: rgba(236,231,220,0.08);
  --accent: #5487ce;
  --accent-soft: rgba(84,135,206,0.16);
  /* Version aclarada de los colores por categoria, para legibilidad como
     texto sobre fondo oscuro (los valores base de THEME_CSS se pensaron
     para fondo claro). */
  --cat-notificacion: #6cb3ba;
  --cat-contestar: #d1694f;
  --cat-audiencia: #5487ce;
  --cat-pruebas: #b49bdb;
  --cat-sentencia: #d1a54f;
  --cat-impugnar: #dd82a4;
  --cat-otra: #b3bdcb;
}
</style>
"""

# Corporativo: azul marino / gris oscuro / blanco -- la lectura que un
# despacho asocia con solidez institucional, en vez de la calidez de
# "expediente legal". Mismo sistema tipografico y de componentes, solo
# cambia la paleta.
CORPORATIVO_CLARO_CSS = """
<style>
:root {
  --ink: #16202e;
  --ink-soft: #4b5a6d;
  --ink-faint: #8996a6;
  --paper: #ffffff;
  --paper-deep: #f3f6fa;
  --paper-inset: #e8edf4;
  --rule: rgba(15,32,54,0.11);
  --rule-soft: rgba(15,32,54,0.06);
  --accent: #1d3a5f;
  --accent-soft: rgba(29,58,95,0.08);
  /* Dorado muy discreto (no metalico/brillante) como acento secundario --
     pedido explicito del cliente junto con navy/blanco/gris. Se usa con
     moderacion: indicador de seccion activa y separador de la marca, nunca
     como color de superficie o de botones. */
  --accent-2: #a5883f;
}
</style>
"""

CORPORATIVO_OSCURO_CSS = """
<style>
:root {
  --ink: #e7ebf1;
  --ink-soft: #b3bdcb;
  --ink-faint: #7c889b;
  --paper: #0c131d;
  --paper-deep: #131b27;
  --paper-inset: #1b2534;
  --rule: rgba(231,235,241,0.13);
  --rule-soft: rgba(231,235,241,0.07);
  --accent: #5487ce;
  --accent-soft: rgba(84,135,206,0.16);
  /* Mismo dorado discreto que en Corporativo claro, aclarado un poco para
     mantener contraste legible sobre el fondo navy oscuro. */
  --accent-2: #c2a35e;
  /* Misma aclarada de --cat-* que CLASICO_DARK_CSS -- incluida aqui tambien
     porque cada bloque de tema solo redefine sus propias variables, no hay
     herencia entre CLASICO_DARK_CSS y CORPORATIVO_OSCURO_CSS. */
  --cat-notificacion: #6cb3ba;
  --cat-contestar: #d1694f;
  --cat-audiencia: #5487ce;
  --cat-pruebas: #b49bdb;
  --cat-sentencia: #d1a54f;
  --cat-impugnar: #dd82a4;
  --cat-otra: #b3bdcb;
}
</style>
"""

if "theme" not in st.session_state:
    st.session_state["theme"] = "clasico"
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

st.markdown(THEME_CSS, unsafe_allow_html=True)
if st.session_state["theme"] == "corporativo":
    st.markdown(
        CORPORATIVO_OSCURO_CSS if st.session_state["dark_mode"] else CORPORATIVO_CLARO_CSS,
        unsafe_allow_html=True,
    )
elif st.session_state["dark_mode"]:
    st.markdown(CLASICO_DARK_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Autenticacion
# ---------------------------------------------------------------------------

if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None

if st.session_state["auth_user"] is None:
    _, col_card, _ = st.columns([1, 1.2, 1])
    with col_card:
        st.markdown(
            """
            <div class="expediente-card">
              <div class="brand brand-lg" style="margin-bottom:1rem;">
                <div class="brand-mark">⚖</div>
                <div>
                  <div class="brand-name">Lex Workspace</div>
                  <div class="brand-tag">Inteligencia jurídica aplicada</div>
                </div>
              </div>
              <div class="expediente-subtitle">Acceso al expediente digital</div>
            """,
            unsafe_allow_html=True,
        )
        tab_login, tab_registro, tab_recuperar = st.tabs(
            ["Iniciar sesión", "Registrarse", "¿Olvidaste tu contraseña?"]
        )

        with tab_login:
            with st.form("login_form"):
                login_username = st.text_input("Usuario")
                login_password = st.text_input("Contraseña", type="password")
                submitted_login = st.form_submit_button("Iniciar sesión", type="primary")
            if submitted_login:
                try:
                    auth.authenticate_user(login_username, login_password)
                    st.session_state["auth_user"] = login_username.strip()
                    st.rerun()
                except auth.InvalidCredentialsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Error al iniciar sesión: {exc}")

        with tab_registro:
            with st.form("registro_form"):
                new_username = st.text_input("Elige un usuario")
                new_password = st.text_input("Elige una contraseña", type="password")
                new_password2 = st.text_input("Confirma la contraseña", type="password")
                new_security_question = st.text_input(
                    "Pregunta de seguridad (para recuperar tu contraseña)"
                )
                new_security_answer = st.text_input("Respuesta secreta")
                submitted_reg = st.form_submit_button("Crear cuenta", type="primary")
            if submitted_reg:
                if new_password != new_password2:
                    st.error("Las contraseñas no coinciden.")
                elif len(new_password) < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                elif not new_security_question.strip() or not new_security_answer.strip():
                    st.error("La pregunta y la respuesta de seguridad son obligatorias.")
                else:
                    try:
                        auth.create_user(
                            new_username, new_password, new_security_question, new_security_answer
                        )
                        st.success("Cuenta creada. Ya puedes iniciar sesión en la otra pestaña.")
                    except auth.UsernameTakenError as exc:
                        st.error(str(exc))
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Error al crear la cuenta: {exc}")

        with tab_recuperar:
            if "recuperar_username" not in st.session_state:
                st.session_state["recuperar_username"] = None
                st.session_state["recuperar_pregunta"] = None

            if st.session_state["recuperar_username"] is None:
                with st.form("recuperar_buscar_form"):
                    buscar_username = st.text_input("Usuario")
                    submitted_buscar = st.form_submit_button("Continuar", type="primary")
                if submitted_buscar:
                    try:
                        pregunta = auth.get_security_question(buscar_username)
                        st.session_state["recuperar_username"] = buscar_username.strip()
                        st.session_state["recuperar_pregunta"] = pregunta
                        st.rerun()
                    except auth.UserNotFoundError as exc:
                        st.error(str(exc))
            else:
                st.info(f"Pregunta de seguridad: **{st.session_state['recuperar_pregunta']}**")
                with st.form("recuperar_reset_form"):
                    respuesta = st.text_input("Tu respuesta")
                    nueva_password = st.text_input("Nueva contraseña", type="password")
                    nueva_password2 = st.text_input(
                        "Confirma la nueva contraseña", type="password"
                    )
                    submitted_reset = st.form_submit_button(
                        "Restablecer contraseña", type="primary"
                    )
                if submitted_reset:
                    if nueva_password != nueva_password2:
                        st.error("Las contraseñas no coinciden.")
                    elif len(nueva_password) < 8:
                        st.error("La contraseña debe tener al menos 8 caracteres.")
                    else:
                        try:
                            auth.reset_password(
                                st.session_state["recuperar_username"], respuesta, nueva_password
                            )
                            st.session_state["recuperar_username"] = None
                            st.session_state["recuperar_pregunta"] = None
                            st.success(
                                "Contraseña restablecida. Ya puedes iniciar sesión en la otra pestaña."
                            )
                        except auth.InvalidSecurityAnswerError as exc:
                            st.error(str(exc))
                        except auth.UserNotFoundError as exc:
                            st.error(str(exc))
                        except ValueError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Error al restablecer la contraseña: {exc}")

                if st.button("Cancelar"):
                    st.session_state["recuperar_username"] = None
                    st.session_state["recuperar_pregunta"] = None
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def save_uploaded_file(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getvalue())
    tmp.close()
    return Path(tmp.name)


def get_provider_config_safe():
    try:
        return config.get_active_provider_config(), None
    except Exception as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.markdown(
    """
    <div class="brand brand-sidebar">
      <div class="brand-mark">⚖</div>
      <div>
        <div class="brand-name">Lex Workspace</div>
        <div class="brand-tag">Inteligencia jurídica</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.markdown(f"Conectado como **{st.session_state['auth_user']}**")
if st.sidebar.button("Cerrar sesión"):
    st.session_state["auth_user"] = None
    st.rerun()

TEMA_LABELS = {"clasico": "Clásico", "corporativo": "Corporativo"}
tema_opciones = list(TEMA_LABELS.keys())
nuevo_tema = st.sidebar.selectbox(
    "Tema",
    options=tema_opciones,
    index=tema_opciones.index(st.session_state["theme"]),
    format_func=lambda k: TEMA_LABELS[k],
)
if nuevo_tema != st.session_state["theme"]:
    st.session_state["theme"] = nuevo_tema
    st.rerun()

nuevo_dark_mode = st.sidebar.toggle("🌙 Modo oscuro", value=st.session_state["dark_mode"])
if nuevo_dark_mode != st.session_state["dark_mode"]:
    st.session_state["dark_mode"] = nuevo_dark_mode
    st.rerun()

st.sidebar.markdown("---")

herramienta = st.sidebar.radio(
    "Elige una herramienta",
    [
        "Análisis de riesgo contractual",
        "Biblioteca jurídica compartida",
        "Redacción de documentos",
        "Plazos y calendario procesal",
        "Línea de tiempo del caso",
    ],
)

st.sidebar.markdown("---")
provider_config, provider_error = get_provider_config_safe()
# Contenedor reservado aca arriba, pero se rellena mas abajo (despues de que
# corra la herramienta seleccionada) para poder mostrar el proveedor que
# realmente respondio en esta corrida -- el principal, o el de failover si
# el principal fallo y legal_research.ask_llm() reintento con el respaldo.
provider_status_placeholder = st.sidebar.container()


# ---------------------------------------------------------------------------
# Vista 1: Analisis de riesgo contractual
# ---------------------------------------------------------------------------

def vista_riesgo_contractual():
    st.header("📄 Análisis de riesgo contractual")
    st.write(
        "Sube un contrato en formato **.pdf** o **.docx** para detectar cláusulas "
        "de alto, medio y bajo riesgo, y generar un reporte descargable."
    )

    uploaded_file = st.file_uploader("Contrato a analizar", type=["pdf", "docx"])
    analizar = st.button("Analizar contrato", type="primary", disabled=uploaded_file is None)

    if not uploaded_file:
        return

    if analizar:
        if provider_error:
            st.error(f"No se puede analizar: {provider_error}")
            return

        tmp_path = save_uploaded_file(uploaded_file)
        try:
            with st.spinner("Extrayendo texto del documento..."):
                try:
                    text = extract_text(tmp_path)
                except ValueError as exc:
                    st.error(str(exc))
                    return

            if not text.strip():
                st.warning(
                    "No se pudo extraer texto del documento. "
                    "¿Está escaneado sin OCR?"
                )
                return

            chunks = chunk_text_contract(text)
            progress_bar = st.progress(0.0, text=f"Analizando fragmento 0/{len(chunks)}...")

            hallazgos = []
            fallos = 0
            for idx, chunk in enumerate(chunks, start=1):
                progress_bar.progress(
                    idx / len(chunks), text=f"Analizando fragmento {idx}/{len(chunks)}..."
                )
                prompt = build_analysis_prompt(chunk)
                try:
                    raw = ask_llm(prompt, provider_config)
                except Exception as exc:
                    fallos += 1
                    st.warning(f"Fallo el análisis del fragmento {idx}/{len(chunks)}: {exc}")
                    continue
                hallazgos.extend(parse_llm_json(raw))

            progress_bar.progress(1.0, text="Análisis completo.")
            hallazgos = dedupe_findings(hallazgos)

            reporte_md = build_report(uploaded_file.name, hallazgos)

            st.session_state["riesgo_hallazgos"] = hallazgos
            st.session_state["riesgo_reporte_md"] = reporte_md
            st.session_state["riesgo_documento"] = uploaded_file.name
            knowledge_base.log_activity(
                st.session_state["auth_user"], "riesgo_contractual", uploaded_file.name
            )

            if fallos:
                st.warning(
                    f"{fallos} fragmento(s) no pudieron analizarse por un error del LLM. "
                    "El reporte se generó solo con los fragmentos exitosos."
                )
        finally:
            tmp_path.unlink(missing_ok=True)

    hallazgos = st.session_state.get("riesgo_hallazgos")
    reporte_md = st.session_state.get("riesgo_reporte_md")

    if reporte_md is None:
        return

    st.subheader("Resultados")

    if not hallazgos:
        st.info(
            "No se detectaron cláusulas del catálogo de riesgo en este documento. "
            "Esto no garantiza la ausencia de riesgo: se recomienda revisión legal manual."
        )
    else:
        conteo = {"alto": 0, "medio": 0, "bajo": 0}
        for h in hallazgos:
            conteo[h["nivel"]] += 1

        col1, col2, col3 = st.columns(3)
        for col, nivel, etiqueta in (
            (col1, "alto", "Alto riesgo"),
            (col2, "medio", "Riesgo medio"),
            (col3, "bajo", "Bajo riesgo"),
        ):
            col.markdown(
                f"""
                <div class="risk-metric" style="--risk-color:{RISK_COLOR[nivel]}">
                  <div class="risk-metric-label">{RISK_EMOJI[nivel]} {etiqueta}</div>
                  <div class="risk-metric-value">{conteo[nivel]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:1.1rem'></div>", unsafe_allow_html=True)

        orden = {"alto": 0, "medio": 1, "bajo": 2}

        for h in sorted(hallazgos, key=lambda x: orden[x["nivel"]]):
            nivel = h["nivel"]
            recomendacion = html.escape(h["recomendacion"] or "Sin recomendación generada.")
            texto = html.escape(h["texto_exacto"] or "—")
            clausula = html.escape(h["clausula"])
            st.markdown(
                f"""
                <div class="finding-card" style="--finding-color:{RISK_COLOR[nivel]}">
                  <div class="finding-head">
                    <span class="finding-tag">{clausula}</span>
                    <span class="finding-level">{RISK_EMOJI[nivel]} {RISK_LABEL[nivel]}</span>
                  </div>
                  <div class="finding-quote">"{texto}"</div>
                  <div class="finding-reco">{recomendacion}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.download_button(
        "⬇️ Descargar reporte (Markdown)",
        data=reporte_md,
        file_name=f"reporte_{Path(st.session_state.get('riesgo_documento', 'contrato')).stem}.md",
        mime="text/markdown",
    )

    with st.expander("Ver reporte completo en Markdown"):
        st.markdown(reporte_md)


# ---------------------------------------------------------------------------
# Vista 2: Investigacion juridica (Q&A)
# ---------------------------------------------------------------------------

def _sample_document_text(chunks: list[str], max_words: int = 4000) -> str:
    words: list[str] = []
    for chunk in chunks:
        words.extend(chunk.split())
        if len(words) >= max_words:
            break
    return " ".join(words[:max_words])


def _analyze_document(document_id: int) -> None:
    """Clasifica el tipo de documento y genera un resumen, una sola vez, y
    lo persiste. Reusa el ask_llm/provider ya configurado en config.py."""
    doc = knowledge_base.get_document(document_id)
    texto = _sample_document_text(doc["chunks"])

    tipo = ask_llm(config.DOCUMENT_TYPE_PROMPT.format(texto=texto), provider_config).strip()
    resumen = ask_llm(config.DOCUMENT_SUMMARY_PROMPT.format(texto=texto), provider_config).strip()

    knowledge_base.set_document_analysis(document_id, tipo, resumen)


def _answer_document_question(document_id: int, pregunta: str) -> str:
    """Q&A acotado a UN documento de la biblioteca, citando el numero de
    fragmento — el mismo comportamiento que legal_research.py original."""
    model = load_embedding_model(config.EMBEDDING_MODEL)
    query_embedding = model.encode([pregunta], convert_to_numpy=True, normalize_embeddings=True)[0]
    retrieved = knowledge_base.retrieve_top_chunks_for_document(document_id, query_embedding)
    if not retrieved:
        return "Este documento no tiene fragmentos indexados todavia."

    prompt = build_prompt(pregunta, retrieved)
    try:
        return ask_llm(prompt, provider_config)
    except Exception as exc:
        return f"Ocurrió un error al consultar el LLM: {exc}"


def _build_library_prompt(pregunta: str, retrieved: list[tuple[str, str, float]]) -> str:
    if not retrieved:
        return (
            "No se encontro ningun fragmento relevante en la biblioteca "
            f"compartida.\n\nPregunta: {pregunta}\n\n"
            "Responde en espanol con tu conocimiento juridico general, "
            "aclarando que no se baso en un documento especifico de la "
            "biblioteca."
        )

    context_blocks = "\n\n".join(
        f'[Documento "{filename}"]\n{chunk}' for filename, chunk, _ in retrieved
    )
    return (
        f"Contexto extraido de la biblioteca compartida:\n\n{context_blocks}\n\n"
        f"Pregunta: {pregunta}\n\n"
        "Responde en espanol, citando el nombre del documento del que "
        "proviene cada dato relevante."
    )


def vista_investigacion():
    st.header("📚 Biblioteca jurídica compartida")
    st.write(
        "Sube documentos para sumarlos a la biblioteca compartida entre "
        "todos los usuarios. Para preguntar sobre su contenido o sobre "
        "temas jurídicos en general, usa el chat en la esquina inferior "
        "derecha — está disponible en cualquier sección de la app."
    )

    uploaded_file = st.file_uploader("Agregar documento a la biblioteca", type=["pdf"], key="research_pdf")
    procesar = st.button(
        "Agregar a la biblioteca", type="primary", disabled=uploaded_file is None
    )

    username = st.session_state["auth_user"]

    if procesar and uploaded_file is not None:
        existing_id = knowledge_base.find_existing_document(uploaded_file.name, uploaded_file.size)
        if existing_id is not None:
            st.info(f"«{uploaded_file.name}» ya está en la biblioteca compartida.")
        else:
            tmp_path = save_uploaded_file(uploaded_file)
            try:
                with st.spinner("Extrayendo texto del documento..."):
                    text = extract_text_from_pdf(str(tmp_path))

                if not text.strip():
                    st.warning(
                        "No se pudo extraer texto del PDF. ¿Está escaneado sin OCR?"
                    )
                    return

                chunks = chunk_text_research(text)

                with st.spinner("Generando embeddings..."):
                    try:
                        model = load_embedding_model(config.EMBEDDING_MODEL)
                        embeddings = embed_chunks(model, chunks)
                    except Exception as exc:
                        st.error(f"No se pudieron generar los embeddings: {exc}")
                        return

                knowledge_base.add_document(
                    uploaded_file.name, uploaded_file.size, username, chunks, embeddings
                )
                st.success(
                    f"«{uploaded_file.name}» agregado a la biblioteca: "
                    f"{len(chunks)} fragmento(s)."
                )
            finally:
                tmp_path.unlink(missing_ok=True)

        knowledge_base.log_activity(username, "investigacion", uploaded_file.name)

    documentos = knowledge_base.list_documents()
    with st.expander(
        f"📖 Documentos en la biblioteca ({len(documentos)})",
        expanded=len(documentos) > 0,
    ):
        if not documentos:
            st.caption("Aún no hay documentos en la biblioteca compartida.")
        else:
            for doc in documentos:
                st.markdown(
                    f"""
                    <div class="finding-card" style="--finding-color:var(--ink-faint)">
                      <div class="finding-head">
                        <span class="finding-tag">{html.escape(doc['filename'])}</span>
                        <span class="finding-level">{doc['chunk_count']} fragmentos</span>
                      </div>
                      <div class="finding-reco">
                        Subido por <strong>{html.escape(doc['uploaded_by'])}</strong>
                        el {doc['uploaded_at'].strftime('%Y-%m-%d %H:%M')}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if doc["document_type"] is None:
                    if st.button("🔍 Analizar", key=f"analyze_{doc['id']}"):
                        with st.spinner("Analizando documento..."):
                            _analyze_document(doc["id"])
                        st.rerun()
                else:
                    st.markdown(
                        f"""
                        <div class="finding-card" style="--finding-color:var(--accent)">
                          <div class="finding-head">
                            <span class="finding-level">{html.escape(doc['document_type'])}</span>
                          </div>
                          <div class="finding-reco">{html.escape(doc['summary']).replace(chr(10), '<br>')}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    with st.form(f"doc_qa_form_{doc['id']}", border=False):
                        doc_pregunta = st.text_input(
                            "Pregunta sobre este documento",
                            key=f"doc_qa_input_{doc['id']}",
                            placeholder=f"Pregunta sobre «{doc['filename']}»...",
                            label_visibility="collapsed",
                        )
                        doc_preguntar = st.form_submit_button("Preguntar")

                    if doc_preguntar and doc_pregunta.strip():
                        with st.spinner("Consultando al LLM..."):
                            respuesta_doc = _answer_document_question(doc["id"], doc_pregunta.strip())
                        st.session_state[f"doc_qa_answer_{doc['id']}"] = respuesta_doc

                    if f"doc_qa_answer_{doc['id']}" in st.session_state:
                        st.markdown(st.session_state[f"doc_qa_answer_{doc['id']}"])

                st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Chat flotante: disponible en cualquier vista de la app (no en el login,
# que ya termina en st.stop() antes de llegar aqui).
# ---------------------------------------------------------------------------

def _answer_library_question(username: str, pregunta: str) -> tuple[str, str]:
    """Devuelve (badge_html, respuesta). Ejecuta embed -> retrieve -> gate ->
    prompt -> LLM, igual que antes, pero como una funcion pura reutilizable
    desde el widget flotante."""
    if provider_error:
        return "", f"No se puede consultar el LLM: {provider_error}"

    try:
        model = load_embedding_model(config.EMBEDDING_MODEL)
        query_embedding = model.encode(
            [pregunta], convert_to_numpy=True, normalize_embeddings=True
        )[0]
        retrieved = knowledge_base.retrieve_top_chunks_global(query_embedding)
        best_score = retrieved[0][2] if retrieved else -1.0

        grounded = best_score >= config.MIN_RELEVANCE_SCORE
        if grounded:
            prompt = _build_library_prompt(pregunta, retrieved)
            fuentes = ", ".join(sorted({fn for fn, _, _ in retrieved}))
            badge = f'<span class="grounding-badge grounded">📎 {html.escape(fuentes)}</span>'
        else:
            prompt = _build_library_prompt(pregunta, [])
            badge = '<span class="grounding-badge">📖 Conocimiento general</span>'

        respuesta = ask_llm(prompt, provider_config, config.LIBRARY_CHAT_SYSTEM_PROMPT)
        return badge, respuesta
    except Exception as exc:
        return "", f"Ocurrió un error al consultar el LLM: {exc}"


def render_floating_chat():
    username = st.session_state["auth_user"]

    if "research_messages" not in st.session_state:
        st.session_state["research_messages"] = knowledge_base.get_chat_history(username)
    if "chat_widget_open" not in st.session_state:
        st.session_state["chat_widget_open"] = False
    if "chat_expanded" not in st.session_state:
        st.session_state["chat_expanded"] = False

    # Boton redondo y panel son estados mutuamente excluyentes de un mismo
    # componente (no dos piezas flotantes superpuestas): al abrir el panel,
    # el cierre se mueve al encabezado del propio panel.
    if not st.session_state["chat_widget_open"]:
        with st.container(key="floating_chat_toggle"):
            if st.button("💬", key="chat_toggle_btn"):
                st.session_state["chat_widget_open"] = True
                st.rerun()
        return

    panel_key = (
        "floating_chat_panel_expanded"
        if st.session_state["chat_expanded"]
        else "floating_chat_panel_compact"
    )
    with st.container(key=panel_key):
        with st.container(key="floating_chat_header_row"):
            col_titulo, col_expandir, col_cerrar = st.columns([5, 1, 1])
            with col_titulo:
                st.markdown(
                    '<div class="floating-chat-title">📚 Biblioteca jurídica</div>',
                    unsafe_allow_html=True,
                )
            with col_expandir:
                expandir_icono = "⤡" if st.session_state["chat_expanded"] else "⤢"
                expandir_ayuda = (
                    "Volver a tamaño compacto"
                    if st.session_state["chat_expanded"]
                    else "Expandir para consultas complejas"
                )
                if st.button(expandir_icono, key="chat_expand_btn", help=expandir_ayuda):
                    st.session_state["chat_expanded"] = not st.session_state["chat_expanded"]
                    st.rerun()
            with col_cerrar:
                if st.button("✕", key="chat_close_btn", help="Cerrar"):
                    st.session_state["chat_widget_open"] = False
                    st.session_state["chat_expanded"] = False
                    st.rerun()

        messages = st.session_state["research_messages"]
        if not messages:
            bubbles_html = '<div class="chat-bubble-empty">Pregunta algo sobre la biblioteca o sobre derecho en general.</div>'
        else:
            bubbles_html = "".join(
                f'<div class="chat-bubble chat-bubble-{msg["role"]}">{msg["content_html"]}</div>'
                if "content_html" in msg
                else f'<div class="chat-bubble chat-bubble-{msg["role"]}">{html.escape(msg["content"])}</div>'
                for msg in messages
            )
        st.markdown(
            f'<div class="floating-chat-messages" id="floating-chat-scroll">{bubbles_html}</div>',
            unsafe_allow_html=True,
        )

        with st.form("floating_chat_form", clear_on_submit=True, border=False):
            pregunta = st.text_input(
                "Pregunta", placeholder="Escribe tu pregunta jurídica...", label_visibility="collapsed"
            )
            enviado = st.form_submit_button("Enviar", type="primary")

    if enviado and pregunta.strip():
        pregunta = pregunta.strip()
        st.session_state["research_messages"].append(
            {"role": "user", "content": pregunta, "content_html": html.escape(pregunta)}
        )
        knowledge_base.log_chat_message(username, "user", pregunta)

        with st.spinner("Consultando al LLM..."):
            badge, respuesta = _answer_library_question(username, pregunta)

        content_html = (badge + "<br>" if badge else "") + html.escape(respuesta).replace("\n", "<br>")
        st.session_state["research_messages"].append(
            {"role": "assistant", "content": respuesta, "content_html": content_html}
        )
        knowledge_base.log_chat_message(username, "assistant", respuesta)
        st.rerun()


# ---------------------------------------------------------------------------
# Vista 3: Redaccion de documentos
# ---------------------------------------------------------------------------

def vista_redaccion():
    st.header("✍️ Redacción de documentos")
    st.write(
        "Genera cartas, contratos y escritos legales completando un "
        "formulario. Streamlit no puede mostrar archivos Word directamente, "
        "así que el borrador se muestra aquí como texto y también puede "
        "descargarse en .docx y .txt."
    )

    username = st.session_state["auth_user"]

    tipo_key = st.selectbox(
        "Tipo de documento",
        options=list(document_drafting.TIPOS_DOCUMENTO.keys()),
        format_func=lambda k: document_drafting.TIPOS_DOCUMENTO[k]["nombre"],
    )
    tipo_info = document_drafting.TIPOS_DOCUMENTO[tipo_key]

    if st.session_state.get("redaccion_tipo_activo") != tipo_key:
        st.session_state["redaccion_tipo_activo"] = tipo_key
        st.session_state.pop("redaccion_borrador", None)

    with st.form("redaccion_datos_form"):
        valores = {}
        for clave, etiqueta, tipo_campo, opcional in tipo_info["campos"]:
            label = f"{etiqueta}" + (" (opcional)" if opcional else "")
            if tipo_campo == "multiline":
                valores[clave] = st.text_area(label, key=f"redaccion_{tipo_key}_{clave}")
            elif tipo_campo == "money":
                valores[clave] = st.text_input(
                    label, key=f"redaccion_{tipo_key}_{clave}", placeholder="ej. 50000"
                )
            elif tipo_campo == "date":
                valores[clave] = st.date_input(
                    label, key=f"redaccion_{tipo_key}_{clave}", value=None, format="DD/MM/YYYY"
                )
            else:
                valores[clave] = st.text_input(label, key=f"redaccion_{tipo_key}_{clave}")
        generar = st.form_submit_button("Generar borrador", type="primary")

    if generar:
        errores = []
        datos = {}
        for clave, etiqueta, tipo_campo, opcional in tipo_info["campos"]:
            valor = valores[clave]

            if tipo_campo == "date":
                if valor is None:
                    if not opcional:
                        errores.append(f"«{etiqueta}» es obligatorio.")
                    datos[clave] = ""
                else:
                    datos[clave] = valor.strftime("%d/%m/%Y")
                continue

            valor = (valor or "").strip()
            if not valor:
                if not opcional:
                    errores.append(f"«{etiqueta}» es obligatorio.")
                datos[clave] = ""
                continue

            if tipo_campo == "money":
                try:
                    datos[clave] = document_drafting.validar_monto(valor)
                except ValueError as exc:
                    errores.append(f"«{etiqueta}»: {exc}")
            elif tipo_campo == "email":
                try:
                    datos[clave] = document_drafting.validar_email(valor)
                except ValueError as exc:
                    errores.append(f"«{etiqueta}»: {exc}")
            else:
                datos[clave] = valor

        if errores:
            for error in errores:
                st.error(error)
        else:
            datos_formateados = document_drafting.formatear_datos_para_prompt(tipo_info, datos)
            prompt = document_drafting.construir_prompt(
                tipo_info["nombre"], tipo_info["enfoque"], datos_formateados
            )
            with st.spinner("Generando borrador con la IA..."):
                borrador = document_drafting.generar_borrador(prompt, provider_config)

            if borrador is None:
                st.error(
                    "No se pudo generar el documento. Verifica la configuración "
                    "del proveedor de LLM en .env."
                )
            else:
                st.session_state["redaccion_borrador"] = borrador
                st.session_state["redaccion_partes"] = document_drafting.extraer_partes(tipo_info, datos)

    borrador = st.session_state.get("redaccion_borrador")
    if not borrador:
        return

    st.subheader("Borrador")
    st.markdown(
        f'<div class="draft-preview">{html.escape(borrador)}</div>',
        unsafe_allow_html=True,
    )

    with st.form("redaccion_cambios_form", border=False):
        instrucciones = st.text_area(
            "¿Quieres hacer cambios? Describe qué ajustar (deja vacío si no)."
        )
        aplicar_cambios = st.form_submit_button("Aplicar cambios")

    if aplicar_cambios and instrucciones.strip():
        prompt_cambios = document_drafting.construir_prompt_cambios(borrador, instrucciones.strip())
        with st.spinner("Regenerando documento con los cambios solicitados..."):
            nuevo_borrador = document_drafting.generar_borrador(prompt_cambios, provider_config)
        if nuevo_borrador is None:
            st.error("No se pudieron aplicar los cambios. Intenta de nuevo.")
        else:
            st.session_state["redaccion_borrador"] = nuevo_borrador
            st.rerun()

    nombre_base = document_drafting.generar_nombre_archivo(tipo_info["nombre"])

    docx_buffer = io.BytesIO()
    document_drafting.exportar_docx(docx_buffer, tipo_info["nombre"], borrador)

    col1, col2 = st.columns(2)
    with col1:
        descargado_docx = st.download_button(
            "⬇️ Descargar .docx",
            data=docx_buffer.getvalue(),
            file_name=f"{nombre_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )
    with col2:
        descargado_txt = st.download_button(
            "⬇️ Descargar .txt",
            data=borrador.encode("utf-8"),
            file_name=f"{nombre_base}.txt",
            mime="text/plain",
        )

    if descargado_docx or descargado_txt:
        partes = st.session_state.get("redaccion_partes", [])
        document_drafting.guardar_historial(tipo_info["nombre"], partes, nombre_base)
        knowledge_base.log_activity(username, "redaccion", tipo_info["nombre"])


# ---------------------------------------------------------------------------
# Vista 4: Plazos y calendario procesal (deadline_extractor.py)
# ---------------------------------------------------------------------------

def _renderizar_tarjeta_fecha(f) -> None:
    hora_txt = f" a las {html.escape(f.hora)}" if f.hora else ""
    fecha_txt = f.fecha.strftime("%d/%m/%Y") if f.fecha else "sin determinar"
    st.markdown(
        f"""
        <div class="finding-card" style="--finding-color:{CATEGORIA_COLOR[f.categoria]}">
          <div class="finding-head">
            <span class="finding-tag">{CATEGORIA_EMOJI[f.categoria]} {html.escape(CATEGORIAS[f.categoria])}</span>
            <span class="finding-level">{fecha_txt}{hora_txt}</span>
          </div>
          <div class="finding-quote">"{html.escape(f.oracion.strip())}"</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _renderizar_tarjeta_plazo(p) -> None:
    if p.fecha_base and p.fecha_limite:
        rango = (
            f"{p.fecha_base.strftime('%d/%m/%Y')} → "
            f"<strong>{p.fecha_limite.strftime('%d/%m/%Y')}</strong>"
        )
        recomendacion = (
            f"Actuar a más tardar el {p.fecha_limite.strftime('%d/%m/%Y')}; "
            "agenda revisión interna con al menos 3 días de margen."
        )
    else:
        rango = "sin fecha de notificación en el documento"
        recomendacion = "Confirma manualmente la fecha de notificación de este plazo."
    st.markdown(
        f"""
        <div class="finding-card" style="--finding-color:{CATEGORIA_COLOR[p.categoria]}">
          <div class="finding-head">
            <span class="finding-tag">{CATEGORIA_EMOJI[p.categoria]} {html.escape(CATEGORIAS[p.categoria])}</span>
            <span class="finding-level">{p.dias} días hábiles</span>
          </div>
          <div class="finding-quote">{rango}</div>
          <div class="finding-reco">{recomendacion}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
DIAS_SEMANA_ES = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"]


def _eventos_por_fecha(fechas: list, plazos: list, nombre_caso: str) -> dict[date, list[dict]]:
    """Agrupa fechas y plazos ya resueltos por dia calendario, para pintarlos
    como "pildoras" en la vista de calendario. La etiqueta incluye el nombre
    del caso (mismo dato que ya cita generar_ics en sus nombres de evento),
    para que la pildora se relacione con el documento del que viene esa
    fecha, no solo con la categoria generica. El color es uno por categoria
    (CATEGORIA_COLOR), igual que en las tarjetas de detalle de abajo."""
    eventos: dict[date, list[dict]] = {}
    for f in fechas:
        if f.fecha is None:
            continue
        eventos.setdefault(f.fecha, []).append({
            "emoji": CATEGORIA_EMOJI[f.categoria],
            "etiqueta": f"{CATEGORIAS[f.categoria]} · {nombre_caso}",
            "color": CATEGORIA_COLOR[f.categoria],
        })
    for p in plazos:
        if p.fecha_limite is None:
            continue
        eventos.setdefault(p.fecha_limite, []).append({
            "emoji": CATEGORIA_EMOJI[p.categoria],
            "etiqueta": f"{CATEGORIAS[p.categoria]} · {nombre_caso}",
            "color": CATEGORIA_COLOR[p.categoria],
        })
    return eventos


def _renderizar_calendario(eventos_por_fecha: dict[date, list[dict]], anio: int, mes: int) -> None:
    """Cuadricula mensual propia (modulo estandar 'calendar', sin libreria de
    terceros) -- monthdatescalendar ya entrega las semanas completas con los
    dias de meses adyacentes para rellenar la grilla, sin calcular alineacion
    a mano."""
    semanas = calendar_module.Calendar(firstweekday=0).monthdatescalendar(anio, mes)
    hoy = date.today()
    max_eventos_visibles = 3

    encabezado = "".join(
        f'<div class="calendario-dia-nombre">{d}</div>' for d in DIAS_SEMANA_ES
    )

    filas_html = []
    for semana in semanas:
        celdas = []
        for dia in semana:
            clases = ["calendario-dia"]
            if dia.month != mes:
                clases.append("calendario-dia-otro-mes")
            if dia == hoy:
                clases.append("calendario-dia-hoy")

            eventos_dia = eventos_por_fecha.get(dia, [])
            pildoras = "".join(
                f'<div class="calendario-evento" style="--evento-color:{ev["color"]}" '
                f'title="{html.escape(ev["etiqueta"])}">'
                f'{ev["emoji"]} {html.escape(ev["etiqueta"])}</div>'
                for ev in eventos_dia[:max_eventos_visibles]
            )
            restantes = len(eventos_dia) - max_eventos_visibles
            if restantes > 0:
                pildoras += f'<div class="calendario-evento-mas">+{restantes} más</div>'

            celdas.append(
                f'<div class="{" ".join(clases)}">'
                f'<div class="calendario-dia-num">{dia.day}</div>'
                f'{pildoras}'
                f'</div>'
            )
        filas_html.append(f'<div class="calendario-semana">{"".join(celdas)}</div>')

    st.markdown(
        f"""
        <div class="calendario">
          <div class="calendario-semana calendario-encabezado">{encabezado}</div>
          {"".join(filas_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _vista_plazos_documento():
    st.write(
        "Sube un documento judicial en formato **.pdf** o **.docx** para detectar "
        "fechas de notificación, audiencias, sentencias y plazos procesales, y "
        "generar un calendario **.ics** listo para importar a Google Calendar, "
        "Outlook o Apple Calendar."
    )

    uploaded_file = st.file_uploader(
        "Documento judicial a analizar", type=["pdf", "docx"], key="plazos_uploader"
    )
    analizar = st.button("Analizar documento", type="primary", disabled=uploaded_file is None)

    if analizar and uploaded_file:
        tmp_path = save_uploaded_file(uploaded_file)
        try:
            with st.spinner("Extrayendo texto del documento..."):
                try:
                    texto = extract_text_plazos(tmp_path)
                except ValueError as exc:
                    st.error(str(exc))
                    return

            if not texto.strip():
                st.warning(
                    "No se pudo extraer texto del documento. ¿Está escaneado sin OCR?"
                )
                return

            with st.spinner("Detectando fechas y plazos (spaCy + regex)..."):
                try:
                    fechas, plazos = extraer_fechas_y_plazos(texto)
                except RuntimeError as exc:
                    st.error(str(exc))
                    return

            if not fechas and not plazos:
                st.warning("No se encontraron fechas ni plazos en este documento.")
                return

            st.session_state["plazos_fechas"] = fechas
            st.session_state["plazos_plazos"] = plazos
            st.session_state["plazos_documento"] = uploaded_file.name
            # Se invalida cualquier calendario/reporte previo: hay que
            # reconfirmar los anios ambiguos antes de volver a generarlos.
            st.session_state.pop("plazos_ics", None)
            st.session_state.pop("plazos_reporte_md", None)
            # No arrastrar el mes de un caso anterior a este documento nuevo.
            st.session_state.pop("plazos_calendario_mes", None)
            st.session_state.pop("plazos_calendario_synced_doc", None)
        finally:
            tmp_path.unlink(missing_ok=True)

    fechas = st.session_state.get("plazos_fechas")
    plazos = st.session_state.get("plazos_plazos")
    if fechas is None:
        return

    st.subheader("Fechas detectadas")

    # Fechas sin anio explicito en el texto original (ej. "15 de enero"): en
    # la CLI esto se resuelve preguntando por terminal (input()); aqui se
    # resuelve con un widget por fecha ambigua antes de poder confirmar.
    anios_elegidos: dict[int, int] = {}
    indices_ambiguos = [idx for idx, f in enumerate(fechas) if f.anio_ambiguo]
    if indices_ambiguos:
        st.warning(
            f"{len(indices_ambiguos)} fecha(s) no incluyen el año en el texto original. "
            "Confirma a qué año corresponde cada una antes de generar el calendario."
        )
        for idx in indices_ambiguos:
            f = fechas[idx]
            col1, col2 = st.columns([3, 1])
            col1.markdown(
                f'**{CATEGORIAS[f.categoria]}** — "{html.escape(f.texto_fecha_cruda)}"  \n'
                f'<span style="color:var(--ink-faint); font-size:0.85rem;">{html.escape(f.oracion.strip())}</span>',
                unsafe_allow_html=True,
            )
            anios_elegidos[idx] = col2.number_input(
                "Año", min_value=1900, max_value=2100, value=date.today().year,
                key=f"plazos_anio_{idx}", label_visibility="collapsed",
            )
        st.markdown("---")

    confirmar = st.button("✅ Confirmar fechas y generar calendario", type="primary")

    if confirmar:
        for idx, f in enumerate(fechas):
            anio_hint = anios_elegidos.get(idx) if f.anio_ambiguo else None
            f.fecha = normalizar_fecha(f.texto_fecha_cruda, anio_hint=anio_hint)

        festivos = cargar_festivos(Path("festivos.json"))
        fecha_notif = fecha_notificacion_principal(fechas)
        calcular_plazos(plazos, fecha_notif, festivos)

        if fecha_notif is None and plazos:
            st.info(
                "No se encontró una fecha de notificación explícita en el documento: "
                "los plazos relativos no pudieron calcularse (no tendrán límite en el calendario)."
            )

        nombre_caso = Path(st.session_state["plazos_documento"]).stem
        calendario = generar_ics(fechas, plazos, nombre_caso)
        reporte_md = generar_reporte_markdown(
            st.session_state["plazos_documento"], fechas, plazos
        )

        st.session_state["plazos_ics"] = calendario.serialize()
        st.session_state["plazos_reporte_md"] = reporte_md
        knowledge_base.log_activity(
            st.session_state["auth_user"], "plazos", st.session_state["plazos_documento"]
        )

    if not fechas and not plazos:
        st.info("No hay fechas ni plazos para mostrar.")
        return

    for f in fechas:
        _renderizar_tarjeta_fecha(f)
    for p in plazos:
        _renderizar_tarjeta_plazo(p)

    ics_data = st.session_state.get("plazos_ics")
    reporte_md = st.session_state.get("plazos_reporte_md")

    if not ics_data and not reporte_md:
        st.caption(
            "Presiona \"Confirmar fechas y generar calendario\" para habilitar la "
            "descarga del calendario .ics y del reporte, y para ver estas fechas "
            "en la pestaña \"Calendario\"."
        )
        return

    nombre_base = Path(st.session_state.get("plazos_documento", "documento")).stem
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Descargar calendario (.ics)",
            data=ics_data,
            file_name=f"plazos_{nombre_base}.ics",
            mime="text/calendar",
            type="primary",
        )
    with col2:
        st.download_button(
            "⬇️ Descargar reporte (Markdown)",
            data=reporte_md,
            file_name=f"reporte_plazos_{nombre_base}.md",
            mime="text/markdown",
        )

    with st.expander("Ver reporte completo en Markdown"):
        st.markdown(reporte_md)


def _vista_plazos_calendario():
    """Pestaña siempre accesible, independiente de en que paso del analisis
    este el usuario -- el marco del calendario (encabezado + navegacion +
    cuadricula) se muestra siempre, aunque este vacio, en vez de aparecer
    recien al final del flujo de la otra pestaña."""
    fechas = st.session_state.get("plazos_fechas") or []
    plazos = st.session_state.get("plazos_plazos") or []
    nombre_caso = Path(st.session_state.get("plazos_documento", "documento")).stem

    eventos_por_fecha = _eventos_por_fecha(fechas, plazos, nombre_caso)

    if not st.session_state.get("plazos_fechas"):
        st.info(
            "Aún no has analizado ningún documento. Ve a la pestaña "
            "\"Analizar documento\" para detectar fechas y verlas aquí."
        )
    elif not eventos_por_fecha:
        st.info(
            "Confirma las fechas en la pestaña \"Analizar documento\" "
            "(botón \"✅ Confirmar fechas y generar calendario\") para verlas aquí."
        )

    # st.tabs ejecuta el cuerpo de AMBAS pestanas en cada rerun (solo oculta
    # con CSS la que no esta activa) -- por eso esta funcion ya corre antes
    # de que existan fechas confirmadas, y una inicializacion "una sola vez"
    # aqui fijaria el mes en el primer render (vacio) y nunca saltaria al
    # mes real una vez confirmadas las fechas en la otra pestana. Se guarda
    # a que documento corresponde el ultimo salto automatico, para saltar
    # de nuevo justo cuando aparecen eventos de un documento nuevo, sin
    # pisar la navegacion manual del usuario en reruns posteriores del
    # mismo documento (ej. al hacer clic en ◀/▶).
    documento_actual = st.session_state.get("plazos_documento")
    if eventos_por_fecha and st.session_state.get("plazos_calendario_synced_doc") != documento_actual:
        primera = min(eventos_por_fecha.keys())
        st.session_state["plazos_calendario_mes"] = (primera.year, primera.month)
        st.session_state["plazos_calendario_synced_doc"] = documento_actual

    if "plazos_calendario_mes" not in st.session_state:
        st.session_state["plazos_calendario_mes"] = (date.today().year, date.today().month)

    anio_mes, mes_mes = st.session_state["plazos_calendario_mes"]

    nav_prev, nav_label, nav_next = st.columns([1, 4, 1])
    with nav_prev:
        if st.button("◀", key="plazos_mes_prev"):
            mes_mes -= 1
            if mes_mes == 0:
                mes_mes, anio_mes = 12, anio_mes - 1
            st.session_state["plazos_calendario_mes"] = (anio_mes, mes_mes)
            st.rerun()
    with nav_label:
        st.markdown(
            f'<div style="text-align:center; font-family:\'Source Serif 4\',serif; '
            f'font-weight:600; font-size:1.1rem; padding-top:0.3rem;">'
            f'{MESES_ES[mes_mes]} {anio_mes}</div>',
            unsafe_allow_html=True,
        )
    with nav_next:
        if st.button("▶", key="plazos_mes_next"):
            mes_mes += 1
            if mes_mes == 13:
                mes_mes, anio_mes = 1, anio_mes + 1
            st.session_state["plazos_calendario_mes"] = (anio_mes, mes_mes)
            st.rerun()

    _renderizar_calendario(eventos_por_fecha, anio_mes, mes_mes)


def vista_plazos():
    st.header("📅 Plazos y calendario procesal")

    tab_documento, tab_calendario = st.tabs(["📄 Analizar documento", "📅 Calendario"])
    with tab_documento:
        _vista_plazos_documento()
    with tab_calendario:
        _vista_plazos_calendario()


# ---------------------------------------------------------------------------
# Vista 5: Linea de tiempo del caso (case_timeline.py)
# ---------------------------------------------------------------------------

def _renderizar_tarjeta_evento_timeline(e: dict) -> None:
    color = case_timeline.CATEGORIA_COLOR.get(e["categoria"], "#666666")
    emoji = case_timeline.CATEGORIA_EMOJI.get(e["categoria"], "📌")
    fecha_txt = e["fecha"] or "sin fecha determinada"
    personas_txt = ", ".join(e["personas"]) if e["personas"] else "—"
    st.markdown(
        f"""
        <div class="finding-card" style="--finding-color:{color}">
          <div class="finding-head">
            <span class="finding-tag">{emoji} {html.escape(e['categoria_label'])}</span>
            <span class="finding-level">{fecha_txt}</span>
          </div>
          <div class="finding-quote">{html.escape(e['descripcion'])}</div>
          <div class="finding-reco">👥 {html.escape(personas_txt)} · 📄 {html.escape(e['fuente'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _renderizar_tarjeta_inconsistencia_timeline(inc: dict) -> None:
    sugerida = f" (fecha sugerida: {inc['fecha_sugerida']})" if inc.get("fecha_sugerida") else ""
    st.markdown(
        f"""
        <div class="finding-card" style="--finding-color:var(--accent-2)">
          <div class="finding-head">
            <span class="finding-tag">🔍 {html.escape(inc['tipo'])}</span>
          </div>
          <div class="finding-quote">{html.escape(inc['descripcion'])}{html.escape(sugerida)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _nombre_archivo_seguro(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "_" for c in texto).strip("_")
    return limpio or "timeline_caso"


def _vista_timeline_documentos():
    st.write(
        "Sube uno o varios documentos (**.pdf**, **.docx**, **.txt**) del mismo caso "
        "para reconstruir su línea de tiempo: eventos con fecha, personas involucradas, "
        "categoría, relaciones entre eventos e inconsistencias."
    )

    uploaded_files = st.file_uploader(
        "Documentos del caso", type=["pdf", "docx", "txt"],
        accept_multiple_files=True, key="timeline_uploader",
    )
    nombre_caso_input = st.text_input("Nombre del caso (opcional)", key="timeline_nombre_caso_input")
    analizar = st.button("Analizar documentos", type="primary", disabled=not uploaded_files)

    if analizar and uploaded_files:
        if provider_error:
            st.error(f"No se puede analizar: {provider_error}")
            return

        # save_uploaded_file() usa un nombre temporal aleatorio (bien para
        # las otras vistas, que no muestran el nombre de archivo en el
        # resultado) -- aqui el nombre original SI importa (es el campo
        # "fuente" de cada evento), asi que se preserva creando el temporal
        # dentro de un directorio propio en vez de con nombre aleatorio.
        tmp_dirs = [Path(tempfile.mkdtemp()) for _ in uploaded_files]
        tmp_paths = []
        for tmp_dir, f in zip(tmp_dirs, uploaded_files):
            tmp_path = tmp_dir / f.name
            tmp_path.write_bytes(f.getvalue())
            tmp_paths.append(tmp_path)
        try:
            progreso = st.progress(0.0, text="Procesando documentos...")
            avance = {"n": 0}

            def _actualizar_progreso(nombre, n_eventos):
                avance["n"] += 1
                progreso.progress(
                    avance["n"] / len(tmp_paths),
                    text=f"{nombre}: {n_eventos} eventos encontrados ({avance['n']}/{len(tmp_paths)})",
                )

            try:
                eventos_ordenados, conteo_por_doc, fallos_extraccion = case_timeline.procesar_documentos(
                    tmp_paths, provider_config, interactivo=False,
                    on_documento_procesado=_actualizar_progreso,
                )
            except ValueError as exc:
                st.warning(str(exc))
                return
            progreso.progress(1.0, text="Extracción completa.")
            if fallos_extraccion:
                for nombre, motivo in fallos_extraccion:
                    st.warning(f"No se pudo procesar **{nombre}**: {motivo}")
        finally:
            for p in tmp_paths:
                p.unlink(missing_ok=True)
            for tmp_dir in tmp_dirs:
                tmp_dir.rmdir()

        with st.spinner("Analizando consistencia y generando narrativa..."):
            analisis = case_timeline.analizar_consistencia(eventos_ordenados, provider_config)

        nombre_caso = nombre_caso_input.strip() or (
            Path(uploaded_files[0].name).stem if len(uploaded_files) == 1 else "Caso judicial"
        )
        datos = case_timeline.construir_datos_timeline(nombre_caso, eventos_ordenados, analisis)

        with st.spinner("Generando gráfico, reporte, presentación y HTML..."):
            png_bytes = case_timeline.generar_grafico_png(datos)
            st.session_state["timeline_datos"] = datos
            st.session_state["timeline_png"] = png_bytes
            st.session_state["timeline_md"] = case_timeline.generar_reporte_markdown(datos)
            st.session_state["timeline_pptx"] = case_timeline.generar_pptx(datos, png_bytes)
            st.session_state["timeline_html"] = case_timeline.generar_html_mermaid(datos)
            st.session_state["timeline_json"] = case_timeline.generar_json(datos)

        st.session_state["timeline_conteo_por_doc"] = conteo_por_doc
        # Anios ambiguos (ej. "20 de febrero" sin anio) se resuelven aqui sin
        # preguntar por evento -- a diferencia de "Plazos y calendario
        # procesal" (pocas fechas por documento), aqui puede haber muchos
        # eventos en varios documentos, y un widget por fecha ambigua seria
        # dificil de usar. Se asume el anio actual (interactivo=False, igual
        # que --no-interactivo en la CLI) y se avisa cuales se asumieron.
        st.session_state["timeline_anios_ambiguos"] = [
            {"texto": e.fecha_cruda, "descripcion": e.descripcion,
             "fecha_asignada": e.fecha.isoformat() if e.fecha else None}
            for e in eventos_ordenados if e.anio_ambiguo
        ]
        knowledge_base.log_activity(
            st.session_state["auth_user"], "timeline",
            ", ".join(f.name for f in uploaded_files),
        )

    datos = st.session_state.get("timeline_datos")
    if datos is None:
        return

    conteo_por_doc = st.session_state.get("timeline_conteo_por_doc", {})
    st.caption(
        f"Último análisis: {len(datos['eventos'])} eventos en {len(conteo_por_doc)} documento(s). "
        "Ve a la pestaña \"Línea de tiempo\" para ver el resultado."
    )
    for nombre, n in conteo_por_doc.items():
        st.caption(f"📄 {nombre}: {n} eventos encontrados")

    ambiguos = st.session_state.get("timeline_anios_ambiguos", [])
    if ambiguos:
        detalle = "; ".join(f'"{a["texto"]}" → {a["fecha_asignada"]}' for a in ambiguos)
        st.warning(
            f"{len(ambiguos)} fecha(s) no incluían el año en el texto original; "
            f"se asumió el año actual: {detalle}. Revisa manualmente si no es correcto."
        )


def _vista_timeline_visual():
    """Pestaña siempre accesible (mismo criterio que la pestaña "Calendario"
    de vista_plazos): estado vacio antes de analizar, se puebla despues."""
    datos = st.session_state.get("timeline_datos")
    if datos is None:
        st.info(
            "Aún no has analizado ningún documento. Ve a la pestaña "
            "\"Documentos\" para generar la línea de tiempo."
        )
        return

    st.subheader(datos["caso"])
    if datos["periodo"]["inicio"]:
        st.caption(f"Periodo: {datos['periodo']['inicio']} a {datos['periodo']['fin']}")

    png_bytes = st.session_state.get("timeline_png")
    if png_bytes:
        st.image(png_bytes, use_container_width=True)

    if datos["narrativa"]:
        st.subheader("📖 Narrativa del caso")
        st.markdown(datos["narrativa"])

    if datos["inconsistencias"]:
        st.subheader("🔍 Inconsistencias encontradas")
        for inc in datos["inconsistencias"]:
            _renderizar_tarjeta_inconsistencia_timeline(inc)

    st.subheader("Eventos")
    for e in datos["eventos"]:
        _renderizar_tarjeta_evento_timeline(e)

    st.subheader("Descargar")
    nombre_base = _nombre_archivo_seguro(datos["caso"])
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Gráfico (.png)", data=st.session_state["timeline_png"],
            file_name=f"{nombre_base}.png", mime="image/png", type="primary",
        )
        st.download_button(
            "⬇️ Reporte (Markdown)", data=st.session_state["timeline_md"],
            file_name=f"{nombre_base}.md", mime="text/markdown",
        )
        st.download_button(
            "⬇️ Datos (.json)", data=st.session_state["timeline_json"],
            file_name=f"{nombre_base}_events.json", mime="application/json",
        )
    with col2:
        st.download_button(
            "⬇️ Presentación (.pptx)", data=st.session_state["timeline_pptx"],
            file_name=f"{nombre_base}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        st.download_button(
            "⬇️ HTML interactivo", data=st.session_state["timeline_html"],
            file_name=f"{nombre_base}.html", mime="text/html",
        )

    with st.expander("Ver reporte completo en Markdown"):
        st.markdown(st.session_state["timeline_md"])


def vista_timeline():
    st.header("🕒 Línea de tiempo del caso")
    tab_documentos, tab_visual = st.tabs(["📂 Documentos", "🕒 Línea de tiempo"])
    with tab_documentos:
        _vista_timeline_documentos()
    with tab_visual:
        _vista_timeline_visual()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if herramienta == "Análisis de riesgo contractual":
    vista_riesgo_contractual()
elif herramienta == "Biblioteca jurídica compartida":
    vista_investigacion()
elif herramienta == "Redacción de documentos":
    vista_redaccion()
elif herramienta == "Plazos y calendario procesal":
    vista_plazos()
else:
    vista_timeline()

render_floating_chat()

with provider_status_placeholder:
    st.subheader("Proveedor de LLM activo")
    if provider_error:
        st.error(f"No se pudo determinar el proveedor de LLM:\n\n{provider_error}")
    else:
        if legal_research.last_provider_used:
            st.session_state["llm_ultimo_proveedor"] = legal_research.last_provider_used
        en_uso = st.session_state.get("llm_ultimo_proveedor") or provider_config
        es_failover = en_uso["provider"] != provider_config["provider"]
        etiqueta = " ⚠️ (failover)" if es_failover else ""
        st.success(f"**{en_uso['provider']}**{etiqueta} — `{en_uso['model']}`")
        if es_failover:
            st.caption(
                f"El proveedor principal (**{provider_config['provider']}**) fallo en la "
                "ultima llamada y se uso el respaldo automaticamente."
            )
