"""
deadline_extractor.py

Extractor de plazos y fechas procesales a partir de un documento judicial
(.pdf o .docx):

1. Recibe la ruta del documento como argumento.
2. Extrae el texto completo (pypdf para PDF, python-docx para DOCX).
3. Usa spaCy ('es_core_news_sm') para segmentar el texto en oraciones, y
   expresiones regulares sobre cada oracion para encontrar fechas explicitas
   y plazos relativos ("N dias para contestar", etc.), clasificandolos en
   una de siete categorias procesales.
4. Normaliza toda fecha encontrada (en cualquier formato: "15 de enero de
   2024", "15/Ene/2024", "15-01-2024", ...) a un objeto date con dateparser.
5. Calcula la fecha limite de cada plazo relativo sumando dias habiles
   (excluyendo sabados, domingos y los festivos de festivos.json) a la
   fecha de notificacion encontrada en el documento.
6. Genera un archivo .ics (con recordatorios a 1 y 3 dias antes) y un
   reporte en Markdown con las tablas de fechas y plazos.

Uso:
    python deadline_extractor.py ruta/al/auto_judicial.pdf
    python deadline_extractor.py ruta/al/auto.docx --festivos mis_festivos.json --no-interactivo

Requiere el modelo de spaCy en espanol instalado una sola vez:
    python -m spacy download es_core_news_sm
"""

import argparse
import json
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import dateparser
import spacy
from docx import Document
from ics import Calendar, Event
from ics.alarm import DisplayAlarm
from pypdf import PdfReader

# La libreria 'ics' 0.7.3 serializa cada alarma internamente con str(alarm),
# lo cual dispara su propio FutureWarning interno (recomendando serialize(),
# que es exactamente lo que hace por dentro) -- es ruido de la libreria, no
# algo accionable en este modulo.
warnings.filterwarnings("ignore", category=FutureWarning, module="ics")

import config  # noqa: F401  (se deja importado para uso futuro: interpretacion de fechas complejas con LLM)

# La consola de Windows por defecto (cp1252) no puede imprimir los emojis
# usados en la salida de este script; se reconfigura a UTF-8 si el stream
# lo permite (stdout puede no soportar reconfigure() si fue redirigido).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# --- Categorias procesales -------------------------------------------------

CATEGORIAS = {
    "notificacion": "Fecha de notificación",
    "plazo_contestar": "Plazo para contestar",
    "audiencia": "Fecha de audiencia",
    "plazo_pruebas": "Plazo para ofrecer pruebas",
    "sentencia": "Fecha de sentencia",
    "plazo_impugnar": "Plazo para impugnar",
    "otra": "Otras fechas relevantes",
}

CATEGORIA_EMOJI = {
    "notificacion": "📅",
    "plazo_contestar": "⚖️",
    "audiencia": "🏛️",
    "plazo_pruebas": "📄",
    "sentencia": "⚖️",
    "plazo_impugnar": "⚠️",
    "otra": "📌",
}

# Un color distinto por categoria, para diferenciarlas de un vistazo en el
# calendario y en las tarjetas de detalle (antes solo habia dos tonos:
# gris para fechas, azul para plazos). Son variables CSS (no hex directo)
# definidas en THEME_CSS/CLASICO_DARK_CSS/CORPORATIVO_OSCURO_CSS en app.py,
# con una version mas clara para los temas oscuros -- mismo patron que
# --accent/--accent-2.
CATEGORIA_COLOR = {
    "notificacion": "var(--cat-notificacion)",
    "plazo_contestar": "var(--cat-contestar)",
    "audiencia": "var(--cat-audiencia)",
    "plazo_pruebas": "var(--cat-pruebas)",
    "sentencia": "var(--cat-sentencia)",
    "plazo_impugnar": "var(--cat-impugnar)",
    "otra": "var(--cat-otra)",
}

# Nombre del modelo de spaCy en espanol (se usa solo para segmentar el
# documento en oraciones y darle contexto a las expresiones regulares).
SPACY_MODEL = "es_core_news_sm"

_MESES = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|"
    "octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic"
)

# Fecha en formato textual: "15 de enero de 2024" o "15 de enero" (sin anio).
_FECHA_TEXTUAL = rf"\d{{1,2}}\s+de\s+(?:{_MESES})\.?(?:\s+de\s+\d{{4}})?"
# Fecha en formato "15/Ene/2024", "15-Ene-2024", "15/enero/2024".
_FECHA_MES_ABREV = rf"\d{{1,2}}[/-](?:{_MESES})[/-]\d{{2,4}}"
# Fecha numerica: "15/01/2024", "15-01-2024", "2024-01-15".
_FECHA_NUMERICA = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}"

DATE_REGEX = re.compile(
    rf"(?:{_FECHA_TEXTUAL}|{_FECHA_MES_ABREV}|{_FECHA_NUMERICA})",
    re.IGNORECASE,
)

# Hora asociada a un evento: "a las 10:00", "a las 10:00 horas", "a las 10:00 AM".
HORA_REGEX = re.compile(
    r"a\s+las\s+(\d{1,2}):(\d{2})\s*(am|pm|horas|hrs)?",
    re.IGNORECASE,
)

# Un anio explicito de 4 digitos (19xx o 20xx) dentro del texto de la fecha.
ANIO_REGEX = re.compile(r"\b(19|20)\d{2}\b")

# Patrones de plazos relativos: "N dias [habiles] para <accion>".
PLAZO_PATTERNS = {
    "plazo_contestar": re.compile(
        r"(\d+)\s*d[ií]as?(?:\s+h[aá]biles)?\s+(?:de\s+plazo\s+)?para\s+contestar",
        re.IGNORECASE,
    ),
    "plazo_pruebas": re.compile(
        r"(\d+)\s*d[ií]as?(?:\s+h[aá]biles)?\s+(?:de\s+plazo\s+)?para\s+ofrecer\s+pruebas",
        re.IGNORECASE,
    ),
    "plazo_impugnar": re.compile(
        r"(\d+)\s*d[ií]as?(?:\s+h[aá]biles)?\s+(?:de\s+plazo\s+)?para\s+impugnar",
        re.IGNORECASE,
    ),
}

# Palabras clave que asignan una oracion con fecha explicita a una categoria.
# Se revisan en este orden (la primera que haga match gana).
CATEGORIA_KEYWORDS = [
    ("notificacion", re.compile(r"notificad[oa]|notificaci[oó]n", re.IGNORECASE)),
    ("audiencia", re.compile(r"audiencia", re.IGNORECASE)),
    ("sentencia", re.compile(r"sentencia", re.IGNORECASE)),
]


# --- Estructuras de datos ---------------------------------------------------

@dataclass
class FechaEncontrada:
    categoria: str
    texto_fecha_cruda: str
    oracion: str
    fecha: date | None = None
    anio_ambiguo: bool = False
    hora: str | None = None  # "HH:MM" en formato 24h, si se detecto


@dataclass
class PlazoCalculado:
    categoria: str
    dias: int
    oracion: str
    fecha_base: date | None = None
    fecha_limite: date | None = None


# --- Extraccion de texto del documento -------------------------------------

def extract_text(path: Path) -> str:
    """Extrae el texto completo de un PDF o DOCX. No incluye OCR: se asume
    un documento judicial con capa de texto (escrito digitalmente o ya
    convertido con OCR previamente)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Formato no soportado: '{suffix}'. Usa un archivo .pdf o .docx")


# --- Dias festivos / dias habiles ------------------------------------------

def cargar_festivos(path: Path) -> set[date]:
    """Carga un archivo festivos.json con la forma {"2024": ["2024-01-01", ...]}
    y devuelve el conjunto de fechas festivas de todos los anios incluidos.
    Si el archivo no existe, se asume que no hay festivos configurados (solo
    se excluyen sabados y domingos del calculo de dias habiles)."""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    festivos = set()
    for _anio, fechas in data.items():
        for fecha_str in fechas:
            festivos.add(datetime.strptime(fecha_str, "%Y-%m-%d").date())
    return festivos


def sumar_dias_habiles(fecha_inicio: date, dias: int, festivos: set[date]) -> date:
    """Suma 'dias' dias habiles (excluye sabados, domingos y festivos) a
    partir de fecha_inicio (sin contar fecha_inicio misma)."""
    actual = fecha_inicio
    contados = 0
    while contados < dias:
        actual += timedelta(days=1)
        if actual.weekday() < 5 and actual not in festivos:
            contados += 1
    return actual


# --- Normalizacion de fechas -------------------------------------------------

_DATEPARSER_SETTINGS = {"DATE_ORDER": "DMY", "STRICT_PARSING": False}


def fecha_le_falta_anio(texto_fecha: str) -> bool:
    """True si el texto de la fecha no trae un anio de 4 digitos explicito
    (ej. "15 de enero" en vez de "15 de enero de 2024") -- dateparser en ese
    caso completa con el anio actual, lo cual puede ser incorrecto."""
    return ANIO_REGEX.search(texto_fecha) is None


def normalizar_fecha(texto_fecha: str, anio_hint: int | None = None) -> date | None:
    """Convierte el texto crudo de una fecha a un objeto date. Si el texto no
    trae anio y se recibe anio_hint (resuelto por el usuario o por
    resolver_anio_ambiguo), se agrega antes de parsear."""
    texto = texto_fecha.strip().rstrip(".")
    if anio_hint and fecha_le_falta_anio(texto):
        texto = f"{texto} de {anio_hint}"
    resultado = dateparser.parse(texto, languages=["es"], settings=_DATEPARSER_SETTINGS)
    return resultado.date() if resultado else None


def resolver_anio_ambiguo_cli(texto_fecha: str, oracion: str) -> int:
    """Le pregunta al usuario por terminal a que anio corresponde una fecha
    sin anio explicito. Usada solo en modo interactivo (CLI); la UI de
    Streamlit resuelve esta misma ambiguedad con un widget en vez de input()."""
    sugerido = date.today().year
    print(f'\n⚠️  La fecha "{texto_fecha}" no incluye el año.')
    print(f'    Contexto: "{oracion.strip()}"')
    respuesta = input(f"    ¿A qué año corresponde? (Enter para usar {sugerido}): ").strip()
    if respuesta.isdigit() and len(respuesta) == 4:
        return int(respuesta)
    return sugerido


# --- Extraccion de fechas y plazos ------------------------------------------

_nlp = None


def _cargar_nlp():
    """Carga (una sola vez, perezosamente) el modelo de spaCy en espanol."""
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load(SPACY_MODEL)
        except OSError as exc:
            raise RuntimeError(
                f"Falta el modelo de spaCy '{SPACY_MODEL}'. Instalalo con:\n"
                f"    python -m spacy download {SPACY_MODEL}"
            ) from exc
    return _nlp


def _extraer_hora(oracion: str) -> str | None:
    match = HORA_REGEX.search(oracion)
    if not match:
        return None
    hora, minuto, sufijo = match.groups()
    hora = int(hora)
    sufijo = (sufijo or "").lower()
    if sufijo == "pm" and hora < 12:
        hora += 12
    elif sufijo == "am" and hora == 12:
        hora = 0
    return f"{hora:02d}:{minuto}"


def _categorizar_oracion(oracion: str) -> str:
    for categoria, patron in CATEGORIA_KEYWORDS:
        if patron.search(oracion):
            return categoria
    return "otra"


def extraer_fechas_y_plazos(texto: str) -> tuple[list[FechaEncontrada], list[PlazoCalculado]]:
    """Segmenta el documento en oraciones con spaCy y aplica, sobre cada una,
    las expresiones regulares de fecha/categoria y de plazos relativos.
    Devuelve (fechas_encontradas, plazos_sin_calcular) -- los plazos aun no
    tienen fecha_limite: eso lo resuelve calcular_plazos() una vez conocida
    la fecha de notificacion."""
    nlp = _cargar_nlp()
    doc = nlp(texto)

    fechas: list[FechaEncontrada] = []
    plazos: list[PlazoCalculado] = []

    for sent in doc.sents:
        oracion = sent.text.strip()
        if not oracion:
            continue

        # Plazos relativos ("5 dias para contestar", etc.) -- no requieren
        # una fecha explicita en la misma oracion, se calculan despues.
        for categoria, patron in PLAZO_PATTERNS.items():
            for match in patron.finditer(oracion):
                plazos.append(PlazoCalculado(
                    categoria=categoria,
                    dias=int(match.group(1)),
                    oracion=oracion,
                ))

        # Fechas explicitas (notificacion, audiencia, sentencia, u otras).
        for date_match in DATE_REGEX.finditer(oracion):
            # rstrip: el patron textual admite un punto opcional tras el mes
            # (para abreviaturas como "Ene."), pero cuando la fecha cae al
            # final de una oracion ese punto es el punto final, no parte de
            # la fecha -- se recorta para que no aparezca en los reportes.
            texto_fecha = date_match.group(0).rstrip(".")
            categoria = _categorizar_oracion(oracion)
            fechas.append(FechaEncontrada(
                categoria=categoria,
                texto_fecha_cruda=texto_fecha,
                oracion=oracion,
                anio_ambiguo=fecha_le_falta_anio(texto_fecha),
                hora=_extraer_hora(oracion) if categoria == "audiencia" else None,
            ))

    return fechas, plazos


def resolver_fechas(fechas: list[FechaEncontrada], interactivo: bool = True) -> None:
    """Normaliza fecha_fecha_cruda -> fecha (date) en cada FechaEncontrada,
    modificando la lista in-place. En modo interactivo, pregunta por
    terminal el anio de las fechas ambiguas; en modo no interactivo, usa el
    anio actual como mejor estimacion (para uso desde la UI de Streamlit,
    que resuelve la ambiguedad con sus propios widgets antes de llamar aqui,
    o que simplemente acepta la estimacion)."""
    for f in fechas:
        anio_hint = None
        if f.anio_ambiguo:
            if interactivo:
                anio_hint = resolver_anio_ambiguo_cli(f.texto_fecha_cruda, f.oracion)
            else:
                anio_hint = date.today().year
        f.fecha = normalizar_fecha(f.texto_fecha_cruda, anio_hint=anio_hint)


def calcular_plazos(
    plazos: list[PlazoCalculado],
    fecha_notificacion: date | None,
    festivos: set[date],
) -> None:
    """Calcula fecha_base y fecha_limite de cada plazo relativo, tomando como
    referencia la fecha de notificacion (el punto de partida procesal
    tipico). Si no hay fecha de notificacion en el documento, los plazos
    quedan sin fecha_limite (se reporta la ausencia en el reporte final)."""
    for p in plazos:
        p.fecha_base = fecha_notificacion
        if fecha_notificacion is not None:
            p.fecha_limite = sumar_dias_habiles(fecha_notificacion, p.dias, festivos)


def fecha_notificacion_principal(fechas: list[FechaEncontrada]) -> date | None:
    """La primera fecha de notificacion encontrada en el documento -- es la
    que ancla el computo de los plazos relativos (contestar, pruebas,
    impugnar), tal como ocurre en la practica procesal real."""
    for f in fechas:
        if f.categoria == "notificacion" and f.fecha is not None:
            return f.fecha
    return None


# --- Generacion de calendario (.ics) ----------------------------------------

# Hora por defecto para eventos que solo tienen fecha (sin hora explicita en
# el documento): 09:00, para que el recordatorio aparezca temprano en el dia.
HORA_POR_DEFECTO = time(9, 0)


def _agregar_recordatorios(evento: Event) -> None:
    """Recordatorios pedidos por el cliente: 1 dia antes y 3 dias antes."""
    evento.alarms = [
        DisplayAlarm(trigger=timedelta(days=-3), display_text=f"Recordatorio: {evento.name} (en 3 días)"),
        DisplayAlarm(trigger=timedelta(days=-1), display_text=f"Recordatorio: {evento.name} (mañana)"),
    ]


def generar_ics(
    fechas: list[FechaEncontrada],
    plazos: list[PlazoCalculado],
    nombre_caso: str,
) -> Calendar:
    """Construye un objeto Calendar (libreria 'ics') con un evento por cada
    fecha encontrada y por cada plazo con fecha_limite calculada."""
    calendario = Calendar()

    for f in fechas:
        if f.fecha is None:
            continue
        etiqueta = CATEGORIAS[f.categoria]
        evento = Event()
        if f.categoria == "audiencia":
            evento.name = f"AUDIENCIA: {nombre_caso}"
        else:
            evento.name = f"{etiqueta}: {nombre_caso}"
        evento.description = f'{etiqueta} -- fuente: "{f.oracion.strip()}"'

        if f.hora:
            hora, minuto = (int(x) for x in f.hora.split(":"))
            evento.begin = datetime.combine(f.fecha, time(hora, minuto))
            evento.duration = timedelta(hours=1)
        else:
            evento.begin = datetime.combine(f.fecha, HORA_POR_DEFECTO)
            evento.make_all_day()

        _agregar_recordatorios(evento)
        calendario.events.add(evento)

    for p in plazos:
        if p.fecha_limite is None:
            continue
        etiqueta = CATEGORIAS[p.categoria]
        evento = Event()
        evento.name = f"PLAZO: {etiqueta} ({nombre_caso})"
        evento.description = (
            f'{etiqueta}: {p.dias} días hábiles desde la notificación '
            f'({p.fecha_base.strftime("%d/%m/%Y")}) -- fuente: "{p.oracion.strip()}"'
        )
        evento.begin = datetime.combine(p.fecha_limite, HORA_POR_DEFECTO)
        evento.make_all_day()
        _agregar_recordatorios(evento)
        calendario.events.add(evento)

    return calendario


# --- Reporte en Markdown -----------------------------------------------------

def _fmt_fecha(f: date | None) -> str:
    return f.strftime("%d/%m/%Y") if f else "_sin determinar_"


def generar_reporte_markdown(
    document_name: str,
    fechas: list[FechaEncontrada],
    plazos: list[PlazoCalculado],
) -> str:
    n_fechas = len([f for f in fechas if f.categoria not in PLAZO_PATTERNS])
    n_plazos = len(plazos)
    n_audiencias = len([f for f in fechas if f.categoria == "audiencia"])

    lines = []
    lines.append("# Reporte de Plazos y Fechas Procesales")
    lines.append("")
    lines.append(f"**Documento analizado:** `{document_name}`  ")
    lines.append(f"**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    lines.append("## 📋 Resumen ejecutivo")
    lines.append("")
    lines.append(
        f"Plazos importantes: **{len(fechas)}** fecha(s), **{n_plazos}** plazo(s) "
        f"calculado(s), **{n_audiencias}** audiencia(s)."
    )
    lines.append("")

    lines.append("## 📅 Fechas encontradas")
    lines.append("")
    if fechas:
        lines.append("| Categoría | Fecha original | Fecha normalizada | Fuente |")
        lines.append("|---|---|---|---|")
        for f in fechas:
            emoji = CATEGORIA_EMOJI[f.categoria]
            fuente = f.oracion.strip().replace("|", "/")
            if len(fuente) > 90:
                fuente = fuente[:87] + "..."
            lines.append(
                f"| {emoji} {CATEGORIAS[f.categoria]} | {f.texto_fecha_cruda} "
                f"| {_fmt_fecha(f.fecha)} | \"{fuente}\" |"
            )
    else:
        lines.append("_No se encontraron fechas explícitas en el documento._")
    lines.append("")

    lines.append("## ⏱️ Plazos calculados")
    lines.append("")
    if plazos:
        lines.append("| Categoría | Días hábiles | Notificación → Límite | Recomendación |")
        lines.append("|---|---|---|---|")
        for p in plazos:
            emoji = CATEGORIA_EMOJI[p.categoria]
            if p.fecha_base and p.fecha_limite:
                rango = f"{_fmt_fecha(p.fecha_base)} → {_fmt_fecha(p.fecha_limite)}"
                recomendacion = (
                    f"Actuar a más tardar el **{_fmt_fecha(p.fecha_limite)}**; "
                    "agenda revisión interna con al menos 3 días de margen."
                )
            else:
                rango = "_sin fecha de notificación en el documento_"
                recomendacion = (
                    "No se pudo calcular el límite: confirma manualmente la "
                    "fecha de notificación de este plazo."
                )
            lines.append(f"| {emoji} {CATEGORIAS[p.categoria]} | {p.dias} | {rango} | {recomendacion} |")
    else:
        lines.append("_No se encontraron plazos relativos (\"N días para...\") en el documento._")
    lines.append("")

    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------

def _imprimir_resumen_consola(fechas: list[FechaEncontrada], plazos: list[PlazoCalculado]) -> None:
    print("\n=== FECHAS ENCONTRADAS ===")
    contador = 1
    for f in fechas:
        emoji = CATEGORIA_EMOJI[f.categoria]
        hora_txt = f" a las {f.hora}" if f.hora else ""
        print(
            f'{contador}. {emoji} {CATEGORIAS[f.categoria]}: {_fmt_fecha(f.fecha)}{hora_txt} '
            f'(Fuente: "{f.texto_fecha_cruda}")'
        )
        contador += 1
    for p in plazos:
        emoji = CATEGORIA_EMOJI[p.categoria]
        limite = f"Límite: {_fmt_fecha(p.fecha_limite)}" if p.fecha_limite else "Límite: sin calcular"
        print(f"{contador}. {emoji} {CATEGORIAS[p.categoria]}: {p.dias} días hábiles → {limite}")
        contador += 1


def procesar_documento(
    path: Path,
    festivos_path: Path,
    interactivo: bool = True,
) -> tuple[list[FechaEncontrada], list[PlazoCalculado]]:
    """Punto de entrada reutilizable (CLI y UI de Streamlit): extrae texto,
    encuentra fechas/plazos, resuelve anios ambiguos y calcula los limites.
    """
    texto = extract_text(path)
    if not texto.strip():
        raise ValueError("No se pudo extraer texto del documento (¿está vacío o escaneado sin OCR?).")

    fechas, plazos = extraer_fechas_y_plazos(texto)
    if not fechas and not plazos:
        raise ValueError("No se encontraron fechas ni plazos en el documento.")

    resolver_fechas(fechas, interactivo=interactivo)
    festivos = cargar_festivos(festivos_path)
    fecha_notif = fecha_notificacion_principal(fechas)
    calcular_plazos(plazos, fecha_notif, festivos)
    return fechas, plazos


def main():
    parser = argparse.ArgumentParser(
        description="Extrae fechas y plazos procesales de un documento judicial y genera un calendario .ics"
    )
    parser.add_argument("document_path", help="Ruta al documento judicial (.pdf o .docx)")
    parser.add_argument(
        "--festivos", default="festivos.json",
        help="Ruta al archivo JSON de días festivos (default: festivos.json)",
    )
    parser.add_argument(
        "--ics", default=None,
        help="Ruta del archivo .ics de salida (default: plazos_<nombre_documento>.ics)",
    )
    parser.add_argument(
        "--reporte", default="reporte_plazos.md",
        help="Ruta del reporte markdown de salida (default: reporte_plazos.md)",
    )
    parser.add_argument(
        "--no-interactivo", action="store_true",
        help="No preguntar por terminal ante fechas con año ambiguo (usa el año actual como estimación)",
    )
    args = parser.parse_args()

    path = Path(args.document_path)
    if not path.exists():
        print(f"No se encontró el archivo: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"📄 Analizando: {path.name}")
    print("🔍 Extrayendo fechas...")

    try:
        fechas, plazos = procesar_documento(
            path,
            Path(args.festivos),
            interactivo=not args.no_interactivo,
        )
    except ValueError as exc:
        print(f"⚠️  {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)

    total = len(fechas) + len(plazos)
    print(f"✅ Encontradas {total} fecha(s)/plazo(s)")

    _imprimir_resumen_consola(fechas, plazos)

    nombre_caso = path.stem
    calendario = generar_ics(fechas, plazos, nombre_caso)
    ics_path = Path(args.ics) if args.ics else Path(f"plazos_{path.stem}.ics")
    ics_path.write_text(calendario.serialize(), encoding="utf-8")

    reporte = generar_reporte_markdown(path.name, fechas, plazos)
    reporte_path = Path(args.reporte)
    reporte_path.write_text(reporte, encoding="utf-8")

    print(f"\n📅 Calendario generado: {ics_path}")
    print(f"📝 Reporte generado: {reporte_path}")
    print("\n✅ ¡Listo! Importa el archivo .ics a tu calendario.")


if __name__ == "__main__":
    main()
