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
    retrieve_top_chunks,
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
    ["Análisis de riesgo contractual", "Investigación jurídica (Q&A sobre PDF)"],
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

def vista_investigacion():
    st.header("🔎 Investigación jurídica (Q&A sobre PDF)")
    st.write(
        "Sube un PDF, genera sus embeddings y luego haz preguntas sobre su "
        "contenido en un formato de chat."
    )

    uploaded_file = st.file_uploader("PDF a consultar", type=["pdf"], key="research_pdf")

    procesar = st.button(
        "Procesar documento", type="primary", disabled=uploaded_file is None
    )

    if procesar and uploaded_file is not None:
        tmp_path = save_uploaded_file(uploaded_file)
        try:
            with st.spinner("Extrayendo texto del PDF..."):
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

            st.session_state["research_chunks"] = chunks
            st.session_state["research_embeddings"] = embeddings
            st.session_state["research_doc_name"] = uploaded_file.name
            st.session_state["research_messages"] = []
            st.success(
                f"Documento procesado: {len(chunks)} fragmento(s) listos para consultar."
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    if "research_chunks" not in st.session_state:
        st.info("Sube y procesa un PDF para comenzar a hacer preguntas.")
        return

    st.caption(f"Documento activo: **{st.session_state.get('research_doc_name', '—')}**")

    if "research_messages" not in st.session_state:
        st.session_state["research_messages"] = []

    for msg in st.session_state["research_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    pregunta = st.chat_input("Escribe tu pregunta sobre el documento...")

    if pregunta:
        st.session_state["research_messages"].append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)

        with st.chat_message("assistant"):
            if provider_error:
                respuesta = f"No se puede consultar el LLM: {provider_error}"
                st.error(respuesta)
            else:
                try:
                    model = load_embedding_model(config.EMBEDDING_MODEL)
                    retrieved = retrieve_top_chunks(
                        model,
                        pregunta,
                        st.session_state["research_chunks"],
                        st.session_state["research_embeddings"],
                    )
                    prompt = build_prompt(pregunta, retrieved)
                    with st.spinner("Consultando al LLM..."):
                        respuesta = ask_llm(prompt, provider_config)
                    st.markdown(respuesta)
                except Exception as exc:
                    respuesta = f"Ocurrió un error al consultar el LLM: {exc}"
                    st.error(respuesta)

        st.session_state["research_messages"].append({"role": "assistant", "content": respuesta})


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if herramienta == "Análisis de riesgo contractual":
    vista_riesgo_contractual()
else:
    vista_investigacion()
