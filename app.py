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

import html
import tempfile
from pathlib import Path

import streamlit as st

import auth
import config
import knowledge_base
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
from legal_research import (
    ask_llm,
    build_prompt,
    chunk_text as chunk_text_research,
    embed_chunks,
    extract_text_from_pdf,
)

st.set_page_config(page_title="Legal AI Tools", page_icon="⚖️", layout="wide")


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
  --accent: #8a3324;
  --accent-soft: rgba(138,51,36,0.08);
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
h1, h2, h3, [data-testid="stMetricValue"] {
  font-family: 'Source Serif 4', serif !important;
  letter-spacing: -0.01em;
}
h1 { font-weight: 600; }

[data-testid="stAppViewContainer"] { background: var(--paper); }

[data-testid="stSidebar"] {
  background: var(--paper-deep);
  border-right: 1px solid var(--rule);
}
[data-testid="stSidebar"] h1 {
  font-size: 1.35rem;
  margin-bottom: 0.1rem;
}
[data-testid="stSidebar"] hr { border-color: var(--rule-soft); margin: 0.9rem 0; }

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

/* Inputs: relleno ligeramente mas oscuro que el entorno (inset) */
[data-testid="stTextInput"] input,
[data-testid="stChatInput"] textarea {
  background: var(--paper-inset) !important;
  border: 1px solid var(--rule) !important;
  color: var(--ink) !important;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}

/* Botones primarios: sello de lacre, no azul SaaS */
button[kind="primary"], button[kind="primaryFormSubmit"] {
  background: var(--accent) !important;
  border: none !important;
  font-weight: 500;
  transition: transform 100ms ease-out;
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
  box-shadow: 0 1px 2px rgba(33,29,26,0.05), 0 4px 16px rgba(33,29,26,0.04);
}
.expediente-title {
  font-family: 'Source Serif 4', serif;
  font-weight: 600;
  font-size: 1.6rem;
  color: var(--ink);
  margin-bottom: 0.15rem;
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
   Sombra marcada a proposito (unica excepcion a "elevacion sutil" del resto
   del sistema): es contenido superpuesto sobre la pagina, no una tarjeta
   mas del flujo, y necesita leerse claramente por encima de todo. */
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
  color: #fff !important;
  font-size: 1.4rem;
  box-shadow: 0 6px 20px rgba(33,29,26,0.25);
  border: none !important;
}

.st-key-floating_chat_panel {
  position: fixed;
  bottom: 96px;
  right: 24px;
  z-index: 999990;
  width: 380px;
  max-width: calc(100vw - 48px);
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(33,29,26,0.22), 0 0 0 1px rgba(33,29,26,0.04);
  overflow: hidden;
}

.floating-chat-header {
  background: var(--accent);
  color: #fff;
  font-family: 'Source Serif 4', serif;
  font-weight: 600;
  font-size: 1rem;
  padding: 0.7rem 1rem;
}

.floating-chat-messages {
  max-height: 340px;
  overflow-y: auto;
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  scrollbar-width: thin;
  scrollbar-color: var(--ink-faint) transparent;
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

.st-key-floating_chat_panel [data-testid="stForm"] {
  border: none !important;
  border-top: 1px solid var(--rule) !important;
  padding: 0.6rem 0.8rem !important;
  border-radius: 0 !important;
}
</style>
"""

st.markdown(THEME_CSS, unsafe_allow_html=True)


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
              <div class="expediente-title">⚖️ Legal AI Tools</div>
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

st.sidebar.title("⚖️ Legal AI Tools")
st.sidebar.markdown(f"Conectado como **{st.session_state['auth_user']}**")
if st.sidebar.button("Cerrar sesión"):
    st.session_state["auth_user"] = None
    st.rerun()
st.sidebar.markdown("---")

herramienta = st.sidebar.radio(
    "Elige una herramienta",
    ["Análisis de riesgo contractual", "Biblioteca jurídica compartida"],
)

st.sidebar.markdown("---")
provider_config, provider_error = get_provider_config_safe()
st.sidebar.subheader("Proveedor de LLM activo")
if provider_error:
    st.sidebar.error(f"No se pudo determinar el proveedor de LLM:\n\n{provider_error}")
else:
    st.sidebar.success(f"**{provider_config['provider']}** — `{provider_config['model']}`")


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

    with st.container(key="floating_chat_toggle"):
        icon = "✕" if st.session_state["chat_widget_open"] else "💬"
        if st.button(icon, key="chat_toggle_btn"):
            st.session_state["chat_widget_open"] = not st.session_state["chat_widget_open"]
            st.rerun()

    if not st.session_state["chat_widget_open"]:
        return

    with st.container(key="floating_chat_panel"):
        st.markdown(
            '<div class="floating-chat-header">📚 Biblioteca jurídica</div>',
            unsafe_allow_html=True,
        )

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
# Router
# ---------------------------------------------------------------------------

if herramienta == "Análisis de riesgo contractual":
    vista_riesgo_contractual()
else:
    vista_investigacion()

render_floating_chat()
