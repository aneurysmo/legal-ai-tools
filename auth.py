"""
auth.py

Autenticacion basica multiusuario (mismo nivel de acceso) respaldada por
Prisma y SQLite. Cada operacion abre y cierra su propia conexion de corta
duracion: las operaciones de auth son poco frecuentes y de bajo volumen,
por lo que no se justifica mantener una conexion persistente compartida
entre las sesiones y threads de Streamlit.
"""

from contextlib import contextmanager

import bcrypt
from prisma import Prisma
from prisma.errors import UniqueViolationError


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


class InvalidCredentialsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class InvalidSecurityAnswerError(Exception):
    pass


def create_user(
    username: str, password: str, security_question: str, security_answer: str
) -> None:
    username = username.strip()
    security_question = security_question.strip()
    if not username or not password or not security_question or not security_answer:
        raise ValueError(
            "Usuario, contrasena, pregunta y respuesta de seguridad son obligatorios."
        )

    password_hash = _hash_password(password)
    security_answer_hash = _hash_password(_normalize_answer(security_answer))
    with get_db() as db:
        try:
            db.user.create(
                data={
                    "username": username,
                    "passwordHash": password_hash,
                    "securityQuestion": security_question,
                    "securityAnswerHash": security_answer_hash,
                }
            )
        except UniqueViolationError:
            raise UsernameTakenError(f"El usuario '{username}' ya existe.")


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
