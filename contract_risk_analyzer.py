"""
contract_risk_analyzer.py

Analizador de riesgo de clausulas contractuales sobre un PDF o DOCX:

1. Recibe la ruta de un contrato (.pdf o .docx) como argumento.
2. Extrae el texto completo del documento.
3. Usa el LLM configurado en config.py (Gemini, OpenAI o Claude) para
   detectar clausulas de riesgo segun un catalogo fijo:
     - Alto riesgo: indemnizacion ilimitada, penalizaciones excesivas,
       confidencialidad perpetua.
     - Riesgo medio: renovacion automatica, exclusividad, subcontratacion.
     - Bajo riesgo: ley aplicable, rescision estandar, notificaciones.
4. Genera un reporte en Markdown (reporte_contrato.md por defecto) con
   resumen ejecutivo, tabla de riesgos, texto exacto de cada clausula y
   recomendacion de accion.

Uso:
    python contract_risk_analyzer.py ruta/al/contrato.pdf
    python contract_risk_analyzer.py ruta/al/contrato.docx -o mi_reporte.md
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from pypdf import PdfReader

import config
from legal_research import ask_llm

# Fragmentos mas grandes que en legal_research.py: aqui no se hace busqueda
# semantica, se recorre el documento completo en bloques para deteccion de
# clausulas.
CHUNK_SIZE_WORDS = 4000

RISK_CLAUSES = {
    "alto": [
        "Indemnizacion ilimitada",
        "Penalizaciones excesivas",
        "Confidencialidad perpetua",
    ],
    "medio": [
        "Renovacion automatica",
        "Exclusividad",
        "Subcontratacion",
    ],
    "bajo": [
        "Ley aplicable",
        "Rescision estandar",
        "Notificaciones",
    ],
}

RISK_EMOJI = {"alto": "🔴", "medio": "🟡", "bajo": "🟢"}
RISK_LABEL = {"alto": "Alto riesgo", "medio": "Riesgo medio", "bajo": "Bajo riesgo"}
RISK_ORDER = {"alto": 0, "medio": 1, "bajo": 2}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Formato no soportado: '{suffix}'. Usa un archivo .pdf o .docx")


def chunk_text(text: str, chunk_size_words: int = CHUNK_SIZE_WORDS) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size_words):
        chunk = " ".join(words[i:i + chunk_size_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks or [""]


def build_analysis_prompt(chunk: str) -> str:
    catalogo = "\n".join(
        f"- {RISK_LABEL[nivel]} ({nivel}): " + ", ".join(clausulas)
        for nivel, clausulas in RISK_CLAUSES.items()
    )
    return (
        "Eres un abogado especializado en analisis de riesgo contractual. "
        "Analiza EXCLUSIVAMENTE el siguiente fragmento de un contrato y detecta "
        "clausulas que correspondan a este catalogo de riesgo:\n\n"
        f"{catalogo}\n\n"
        "Responde UNICAMENTE con un arreglo JSON (sin texto adicional, sin "
        "bloques de codigo markdown), donde cada elemento representa una "
        "clausula de riesgo encontrada y tiene esta forma exacta:\n"
        '[{"nivel": "alto|medio|bajo", "clausula": "nombre exacto segun el '
        'catalogo anterior", "texto_exacto": "cita textual y literal del '
        'contrato, sin resumir", "recomendacion": "accion concreta para '
        'mitigar o gestionar el riesgo"}]\n\n'
        "Si el fragmento no contiene ninguna clausula del catalogo, responde "
        "exactamente: []\n\n"
        f"Fragmento del contrato:\n\n{chunk}"
    )


def parse_llm_json(raw: str) -> list[dict]:
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    hallazgos = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nivel = str(item.get("nivel", "")).strip().lower()
        clausula = str(item.get("clausula", "")).strip()
        if nivel not in RISK_CLAUSES or not clausula:
            continue
        hallazgos.append({
            "nivel": nivel,
            "clausula": clausula,
            "texto_exacto": str(item.get("texto_exacto", "")).strip(),
            "recomendacion": str(item.get("recomendacion", "")).strip(),
        })
    return hallazgos


def analyze_document(text: str, provider_config: dict) -> list[dict]:
    chunks = chunk_text(text)
    hallazgos = []
    for idx, chunk in enumerate(chunks, start=1):
        print(f"Analizando fragmento {idx}/{len(chunks)}...")
        prompt = build_analysis_prompt(chunk)
        try:
            raw = ask_llm(prompt, provider_config)
        except Exception as exc:
            print(f"  Aviso: fallo el analisis del fragmento {idx}: {exc}", file=sys.stderr)
            continue
        hallazgos.extend(parse_llm_json(raw))
    return hallazgos


def dedupe_findings(hallazgos: list[dict]) -> list[dict]:
    vistos = set()
    unicos = []
    for h in hallazgos:
        clave = (h["nivel"], h["clausula"].lower(), h["texto_exacto"].lower())
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(h)
    return unicos


def build_report(document_name: str, hallazgos: list[dict]) -> str:
    conteo = {"alto": 0, "medio": 0, "bajo": 0}
    for h in hallazgos:
        conteo[h["nivel"]] += 1
    total = len(hallazgos)

    lines = []
    lines.append("# Reporte de Analisis de Riesgo Contractual")
    lines.append("")
    lines.append(f"**Documento analizado:** `{document_name}`  ")
    lines.append(f"**Fecha de generacion:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    lines.append("## 📋 Resumen ejecutivo")
    lines.append("")
    if total == 0:
        lines.append(
            "No se detectaron clausulas del catalogo de riesgo analizado en este "
            "documento. Esto **no garantiza la ausencia de riesgo**: se recomienda "
            "una revision legal manual completa."
        )
    else:
        lines.append(
            f"Se identificaron **{total}** clausula(s) de riesgo en el documento: "
            f"{RISK_EMOJI['alto']} **{conteo['alto']}** de alto riesgo, "
            f"{RISK_EMOJI['medio']} **{conteo['medio']}** de riesgo medio y "
            f"{RISK_EMOJI['bajo']} **{conteo['bajo']}** de bajo riesgo."
        )
        if conteo["alto"] > 0:
            lines.append("")
            lines.append(
                "⚠️ **Se recomienda revision prioritaria por un abogado antes de "
                "firmar**, dado que se detectaron clausulas de alto riesgo."
            )
    lines.append("")

    lines.append("## 📊 Tabla de riesgos encontrados")
    lines.append("")
    if hallazgos:
        lines.append("| Nivel | Clausula | Recomendacion |")
        lines.append("|---|---|---|")
        for h in sorted(hallazgos, key=lambda x: RISK_ORDER[x["nivel"]]):
            recomendacion_corta = h["recomendacion"].replace("\n", " ") or "_Sin recomendacion generada._"
            lines.append(
                f"| {RISK_EMOJI[h['nivel']]} {RISK_LABEL[h['nivel']]} "
                f"| {h['clausula']} | {recomendacion_corta} |"
            )
    else:
        lines.append("_No se encontraron clausulas de riesgo en el documento._")
    lines.append("")

    for nivel in ("alto", "medio", "bajo"):
        del_nivel = [h for h in hallazgos if h["nivel"] == nivel]
        lines.append(f"## {RISK_EMOJI[nivel]} {RISK_LABEL[nivel]}")
        lines.append("")
        if not del_nivel:
            lines.append(f"_No se encontraron clausulas de {RISK_LABEL[nivel].lower()} en el documento._")
            lines.append("")
            continue
        for h in del_nivel:
            lines.append(f"### {h['clausula']}")
            lines.append("")
            lines.append("**Texto exacto de la clausula:**")
            lines.append("")
            texto = h["texto_exacto"] or "_El modelo no devolvio una cita textual para esta clausula._"
            lines.append(f"> {texto}")
            lines.append("")
            recomendacion = h["recomendacion"] or "_Sin recomendacion generada._"
            lines.append(f"**Recomendacion de accion:** {recomendacion}")
            lines.append("")

    lines.append("## 🔍 Clausulas del catalogo no encontradas")
    lines.append("")
    encontradas = {h["clausula"].strip().lower() for h in hallazgos}
    faltantes = [
        (nivel, clausula)
        for nivel, clausulas in RISK_CLAUSES.items()
        for clausula in clausulas
        if clausula.strip().lower() not in encontradas
    ]
    if faltantes:
        lines.append("Las siguientes clausulas del catalogo **no fueron detectadas** en el documento:")
        lines.append("")
        for nivel, clausula in faltantes:
            lines.append(f"- {RISK_EMOJI[nivel]} {clausula}")
    else:
        lines.append("Se detectaron clausulas de todas las categorias del catalogo.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analisis de riesgo de clausulas contractuales")
    parser.add_argument("document_path", help="Ruta al contrato (.pdf o .docx)")
    parser.add_argument(
        "-o", "--output", default="reporte_contrato.md",
        help="Ruta del reporte markdown de salida (default: reporte_contrato.md)",
    )
    args = parser.parse_args()

    path = Path(args.document_path)
    if not path.exists():
        print(f"No se encontro el archivo: {path}", file=sys.stderr)
        sys.exit(1)

    provider_config = config.get_active_provider_config()
    print(f"Proveedor de LLM activo: {provider_config['provider']} ({provider_config['model']})")

    print(f"Leyendo documento: {path}")
    try:
        text = extract_text(path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    if not text.strip():
        print("No se pudo extraer texto del documento (¿esta escaneado sin OCR?).", file=sys.stderr)
        sys.exit(1)

    hallazgos = dedupe_findings(analyze_document(text, provider_config))

    reporte = build_report(path.name, hallazgos)
    output_path = Path(args.output)
    output_path.write_text(reporte, encoding="utf-8")

    print(f"\nReporte generado en: {output_path.resolve()}")
    print(f"Total de clausulas de riesgo encontradas: {len(hallazgos)}")


if __name__ == "__main__":
    main()
