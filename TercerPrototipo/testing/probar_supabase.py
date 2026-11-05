"""Diagnóstico de Supabase para ejecutar directamente en la Raspberry."""

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

from Tareas.supabase.cliente import (
    cargar_credenciales_supabase,
    crear_cliente_supabase,
    describir_error_supabase,
)


raiz = Path(__file__).resolve().parents[1]
with (raiz / "config/config.yaml").open(
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)

print("Python:", sys.version.split()[0])

try:
    credenciales = cargar_credenciales_supabase()
    host = urlparse(credenciales["SUPABASE_URL"]).hostname
    socket.getaddrinfo(host, 443)
    print("DNS: correcto")

    cliente = crear_cliente_supabase(config)
    print("Autenticación: correcta")

    respuesta_personas = (
        cliente.table("people")
        .select("id", count="exact")
        .limit(1)
        .execute()
    )
    print(
        "Tabla people: accesible; filas:",
        respuesta_personas.count,
    )

    respuesta_embeddings = (
        cliente.table("face_embeddings")
        .select("person_id", count="exact")
        .limit(1)
        .execute()
    )
    print(
        "Tabla face_embeddings: accesible; filas:",
        respuesta_embeddings.count,
    )

except Exception as error:
    print(
        "DIAGNOSTICO SUPABASE:",
        describir_error_supabase(error),
    )
    sys.exit(1)

print("Conexión de Supabase: correcta")
