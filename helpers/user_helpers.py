import base64
import random
import re
from datetime import datetime

from flask import session
from database import get_db_connection


def limpiar_nombre(texto):
    return re.sub(r"[^\w\-]", "_", texto)


def obtener_usuario_sesion():
    if not session.get("user_id"):
        return None
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id_persona, p.nombre, p.apellido, p.foto
        FROM usuarios u
        JOIN personas p ON u.id_persona = p.id_persona
        WHERE u.id_usuario = %s
    """, (session.get("user_id"),))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()

    if usuario and usuario.get("foto"):
        if isinstance(usuario["foto"], (bytes, bytearray)):
            usuario["foto"] = base64.b64encode(usuario["foto"]).decode("utf-8")
    elif usuario:
        usuario["foto"] = None

    return usuario


def generar_carnet_unico():
    yy = datetime.now().strftime("%y")
    prefijo = f"7691-{yy}-"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        while True:
            numero_random = random.randint(10000, 99999)
            carnet = f"{prefijo}{numero_random}"
            cursor.execute("SELECT id_persona FROM personas WHERE carnet = %s", (carnet,))
            if cursor.fetchone() is None:
                return carnet
    finally:
        cursor.close()
        conn.close()
