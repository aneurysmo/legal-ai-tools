"""
prepare_prisma_schema.py

Genera prisma/schema.prisma a partir de prisma/schema.prisma.template,
reemplazando el placeholder __DB_PROVIDER__ por el valor de la variable de
entorno DB_PROVIDER (default: "sqlite", para no romper el flujo de
desarrollo local existente).

Se ejecuta ANTES de cualquier comando de Prisma ('prisma generate',
'prisma db push'), tanto en desarrollo local como en el build de Docker,
porque Prisma no permite que el 'provider' del datasource sea dinamico via
env() -- solo la 'url' lo admite. Este script es el mecanismo que permite
elegir el proveedor (sqlite / postgresql) por ambiente sin editar el schema
a mano.

Uso:
    python scripts/prepare_prisma_schema.py

Variables de entorno relevantes (leidas desde .env si existe, igual que
config.py):
    DB_PROVIDER  "sqlite" (default) o "postgresql"
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

VALID_PROVIDERS = {"sqlite", "postgresql"}

PRISMA_DIR = Path(__file__).resolve().parent.parent / "prisma"
TEMPLATE_PATH = PRISMA_DIR / "schema.prisma.template"
OUTPUT_PATH = PRISMA_DIR / "schema.prisma"


def main() -> None:
    provider = os.getenv("DB_PROVIDER", "sqlite").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise SystemExit(
            f"DB_PROVIDER='{provider}' invalido. Usa 'sqlite' o 'postgresql'."
        )

    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"No se encontro la plantilla: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    schema = template.replace("__DB_PROVIDER__", provider)
    OUTPUT_PATH.write_text(schema, encoding="utf-8")

    print(f"prisma/schema.prisma generado con provider='{provider}'.")
    if provider == "sqlite":
        print("(Uso local/desarrollo. Para despliegue en la nube, usa DB_PROVIDER=postgresql.)")


if __name__ == "__main__":
    main()
