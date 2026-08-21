"""
auth.py

Autenticacion basica multiusuario (mismo nivel de acceso) respaldada por
Prisma y SQLite. Cada operacion abre y cierra su propia conexion de corta
duracion: las operaciones de auth son poco frecuentes y de bajo volumen,
por lo que no se justifica mantener una conexion persistente compartida
entre las sesiones y threads de Streamlit.
"""

from contextlib import contextmanager
from pathlib import Path

import bcrypt
from prisma import Prisma
from prisma.errors import UniqueViolationError

# --- Avatares ---
# El set de avatares es curado y estatico (ver assets/avatars/), viaja
# empaquetado con la app (mismo Docker image / repo para demo y prod). Por
# eso en la base de datos solo se guarda el ID del avatar elegido (nombre de
# archivo sin extension, ej. "lawyer-01-Santiago"), NO el contenido SVG en
# si -- evita duplicar el mismo texto en cada fila de usuario y mantiene el
# tamano de la tabla User minimo, sin necesitar storage externo.
AVATARS_DIR = Path(__file__).resolve().parent / "assets" / "avatars"
DEFAULT_AVATAR_ID = "default-generic"


def list_avatar_ids() -> list[str]:
    """IDs de los avatares elegibles por el usuario (excluye el default)."""
    if not AVATARS_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in AVATARS_DIR.glob("*.svg") if p.stem != DEFAULT_AVATAR_ID
    )


def get_avatar_svg(avatar_id: str) -> str:
    """Contenido SVG del avatar por su ID. Cae al default si no existe/es invalido."""
    safe_id = avatar_id if avatar_id and "/" not in avatar_id and "\\" not in avatar_id else DEFAULT_AVATAR_ID
    path = AVATARS_DIR / f"{safe_id}.svg"
    if not path.is_file():
        path = AVATARS_DIR / f"{DEFAULT_AVATAR_ID}.svg"
    return path.read_text(encoding="utf-8")


@contextmanager
def get_db():
    db = Prisma()
    db.connect()
    try:
        yield db
    finally:
        db.disconnect()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _normalize_answer(answer: str) -> str:
    return answer.strip().lower()


class UsernameTakenError(Exception):
    pass


class EmailTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class InvalidSecurityAnswerError(Exception):
    pass


def create_user(
    username: str,
    password: str,
    security_question: str,
    security_answer: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    username = username.strip()
    security_question = security_question.strip()
    email = email.strip().lower()
    first_name = first_name.strip() if first_name and first_name.strip() else None
    last_name = last_name.strip() if last_name and last_name.strip() else None

    if not username or not password or not security_question or not security_answer:
        raise ValueError(
            "Usuario, contrasena, pregunta y respuesta de seguridad son obligatorios."
        )
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Ingresa un correo electronico valido.")

    password_hash = _hash_password(password)
    security_answer_hash = _hash_password(_normalize_answer(security_answer))
    with get_db() as db:
        # Se verifica username/email por separado antes del insert para poder
        # distinguir cual de los dos ya existe (UniqueViolationError de Prisma
        # no siempre expone de forma simple que columna la disparo).
        if db.user.find_unique(where={"username": username}) is not None:
            raise UsernameTakenError(f"El usuario '{username}' ya existe.")
        if db.user.find_unique(where={"email": email}) is not None:
            raise EmailTakenError(f"El correo '{email}' ya esta registrado.")

        try:
            db.user.create(
                data={
                    "username": username,
                    "email": email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "passwordHash": password_hash,
                    "securityQuestion": security_question,
                    "securityAnswerHash": security_answer_hash,
                }
            )
        except UniqueViolationError:
            raise UsernameTakenError(f"El usuario '{username}' ya existe.")


def update_avatar(username: str, avatar_id: str) -> None:
    valid_ids = set(list_avatar_ids()) | {DEFAULT_AVATAR_ID}
    if avatar_id not in valid_ids:
        raise ValueError(f"Avatar invalido: '{avatar_id}'.")
    with get_db() as db:
        db.user.update(where={"username": username.strip()}, data={"avatar": avatar_id})


def get_user_avatar(username: str) -> str:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})
    if user is None:
        return DEFAULT_AVATAR_ID
    return user.avatar or DEFAULT_AVATAR_ID


def get_user_profile(username: str) -> dict:
    """Datos de perfil editables desde la UI (email, nombres, apellidos, avatar)."""
    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})
    if user is None:
        raise UserNotFoundError(f"El usuario '{username}' no existe.")
    return {
        "username": user.username,
        "email": user.email,
        "firstName": user.firstName or "",
        "lastName": user.lastName or "",
        "avatar": user.avatar or DEFAULT_AVATAR_ID,
    }


def update_profile(
    username: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    username = username.strip()
    email = email.strip().lower()
    first_name = first_name.strip() if first_name and first_name.strip() else None
    last_name = last_name.strip() if last_name and last_name.strip() else None

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Ingresa un correo electronico valido.")

    with get_db() as db:
        existing = db.user.find_unique(where={"email": email})
        if existing is not None and existing.username != username:
            raise EmailTakenError(f"El correo '{email}' ya esta registrado por otro usuario.")

        db.user.update(
            where={"username": username},
            data={"email": email, "firstName": first_name, "lastName": last_name},
        )


def authenticate_user(username: str, password: str) -> bool:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})

    if user is None or not _verify_password(password, user.passwordHash):
        raise InvalidCredentialsError("Usuario o contrasena incorrectos.")

    return True


def get_security_question(username: str) -> str:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})

    if user is None:
        raise UserNotFoundError(f"El usuario '{username}' no existe.")

    return user.securityQuestion


def reset_password(username: str, security_answer: str, new_password: str) -> None:
    if not new_password:
        raise ValueError("La nueva contrasena es obligatoria.")

    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})

        if user is None:
            raise UserNotFoundError(f"El usuario '{username}' no existe.")

        if not _verify_password(_normalize_answer(security_answer), user.securityAnswerHash):
            raise InvalidSecurityAnswerError("Respuesta de seguridad incorrecta.")

        db.user.update(
            where={"username": user.username},
            data={"passwordHash": _hash_password(new_password)},
        )
