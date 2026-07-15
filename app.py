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
# Autenticacion
# ---------------------------------------------------------------------------

if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None

if st.session_state["auth_user"] is None:
    st.title("⚖️ Legal AI Tools")
    tab_login, tab_registro = st.tabs(["Iniciar sesión", "Registrarse"])

    with tab_login:
        with st.form("login_form"):
            login_username = st.text_input("Usuario")
            login_password = st.text_input("Contraseña", type="password")
            submitted_login = st.form_submit_button("Iniciar sesión")
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
            submitted_reg = st.form_submit_button("Crear cuenta")
        if submitted_reg:
            if new_password != new_password2:
                st.error("Las contraseñas no coinciden.")
            elif len(new_password) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            else:
                try:
                    auth.create_user(new_username, new_password)
                    st.success("Cuenta creada. Ya puedes iniciar sesión en la otra pestaña.")
                except auth.UsernameTakenError as exc:
                    st.error(str(exc))
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Error al crear la cuenta: {exc}")

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
        col1.metric(f"{RISK_EMOJI['alto']} Alto riesgo", conteo["alto"])
        col2.metric(f"{RISK_EMOJI['medio']} Riesgo medio", conteo["medio"])
        col3.metric(f"{RISK_EMOJI['bajo']} Bajo riesgo", conteo["bajo"])

        orden = {"alto": 0, "medio": 1, "bajo": 2}
        color = {"alto": "#fde2e2", "medio": "#fff3cd", "bajo": "#d9f2e3"}

        rows_html = ""
        for h in sorted(hallazgos, key=lambda x: orden[x["nivel"]]):
            recomendacion = (h["recomendacion"] or "Sin recomendación generada.").replace("\n", " ")
            texto = (h["texto_exacto"] or "—").replace("\n", " ")
            rows_html += (
                f"<tr style='background-color:{color[h['nivel']]}'>"
                f"<td style='padding:6px'>{RISK_EMOJI[h['nivel']]} {RISK_LABEL[h['nivel']]}</td>"
                f"<td style='padding:6px'>{h['clausula']}</td>"
                f"<td style='padding:6px'>{texto}</td>"
                f"<td style='padding:6px'>{recomendacion}</td>"
                f"</tr>"
            )

        table_html = (
            "<table style='width:100%; border-collapse:collapse;'>"
            "<tr>"
            "<th style='text-align:left; padding:6px'>Nivel</th>"
            "<th style='text-align:left; padding:6px'>Cláusula</th>"
            "<th style='text-align:left; padding:6px'>Texto exacto</th>"
            "<th style='text-align:left; padding:6px'>Recomendación</th>"
            "</tr>" + rows_html + "</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

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
