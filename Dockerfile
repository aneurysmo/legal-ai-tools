# Dockerfile base para legal-ai-tools. Es el MISMO para demo y produccion —
# lo unico que cambia entre ambientes son las variables de entorno pasadas
# al correr el contenedor (ver .env.demo.example / .env.prod.example y
# README.md > "Ambientes (demo / producción)").
#
# Build:
#   docker build -t legal-ai-tools .
# Run local de prueba:
#   docker run -p 8501:8501 --env-file .env.demo legal-ai-tools

FROM python:3.11-slim AS base

# --- Dependencias de sistema ---
# - tesseract-ocr + tesseract-ocr-spa: OCR de respaldo para PDFs escaneados
#   (ver legal_research.py:_ocr_pdf). Liviano (~30-50 MB), no requiere Windows.
# - libgl1: requerido por PyMuPDF/Pillow para procesamiento de imagenes.
# - build-essential: headers de compilacion que algunas dependencias de
#   Python (ej. componentes nativos de spaCy) pueden necesitar en el build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Dependencias de Python ---
# Copiar solo requirements.txt primero aprovecha el cache de capas de Docker:
# si el codigo cambia pero no las dependencias, este paso no se re-ejecuta.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El modelo de spaCy en espanol (es_core_news_sm, usado por
# deadline_extractor.py) ya viene incluido en requirements.txt como wheel
# instalable via pip -- no hace falta 'python -m spacy download' aparte.
# (Se fijo asi para que el mismo requirements.txt sirva tambien en
# plataformas sin paso de build personalizado, como Streamlit Community
# Cloud -- ver comentario en requirements.txt.)

# --- Codigo de la aplicacion ---
COPY . .

# --- Prisma: generar schema + cliente ---
# DB_PROVIDER por defecto en la imagen es "postgresql" porque cualquier
# despliegue en la nube (demo o produccion) usa una base de datos gestionada
# externa -- SQLite no persiste en un contenedor efimero (ver README.md >
# "Notas de despliegue en la nube"). Se puede sobreescribir en build time
# con --build-arg DB_PROVIDER=sqlite si se necesita para un caso puntual.
ARG DB_PROVIDER=postgresql
ENV DB_PROVIDER=${DB_PROVIDER}
RUN python scripts/prepare_prisma_schema.py && \
    prisma generate --schema=prisma/schema.prisma

# --- Runtime ---
EXPOSE 8501

# Streamlit necesita bindear a 0.0.0.0 (no localhost) para ser accesible
# desde fuera del contenedor, y respetar el puerto que la plataforma cloud
# inyecte via la variable de entorno PORT (Cloud Run, Render, etc.) cuando
# exista, con 8501 como default para correr local.
ENV PORT=8501
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true
