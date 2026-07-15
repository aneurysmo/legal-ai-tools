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


class UsernameTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


def create_user(username: str, password: str) -> None:
    username = username.strip()
    if not username or not password:
        raise ValueError("Usuario y contrasena son obligatorios.")

    password_hash = _hash_password(password)
    with get_db() as db:
        try:
            db.user.create(data={"username": username, "passwordHash": password_hash})
        except UniqueViolationError:
            raise UsernameTakenError(f"El usuario '{username}' ya existe.")


def authenticate_user(username: str, password: str) -> bool:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username.strip()})

    if user is None or not _verify_password(password, user.passwordHash):
        raise InvalidCredentialsError("Usuario o contrasena incorrectos.")

    return True
