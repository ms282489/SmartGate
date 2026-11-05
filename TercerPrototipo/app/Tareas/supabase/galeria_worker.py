"""Sincroniza Supabase con la galería local sin bloquear el pipeline."""

import time
from pathlib import Path

import cv2
import numpy as np

from Tareas.reconocimiento.galeria import (
    galeria_compartida,
    galerias_equivalentes,
    guardar_respaldo_local,
)
from Tareas.supabase.cliente import (
    crear_cliente_supabase,
    describir_error_supabase,
)
from Tareas.supabase.rostros_sync import sincronizar_rostros_supabase


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_MODELO = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "reconocimiento"
    / "face_recognition_sface_2021dec.onnx"
)


def cargar_personas_supabase(
    config,
    reconocedor,
    cliente=None,
    sincronizar_fotos=True,
):
    """Obtiene una instantánea completa de las personas habilitadas."""

    if cliente is None:
        cliente = crear_cliente_supabase(config)

    if sincronizar_fotos:
        try:
            sincronizar_rostros_supabase(cliente, config, reconocedor)
        except Exception as error:
            # Storage puede fallar y aun así pueden utilizarse los
            # embeddings que ya estaban almacenados en la base.
            print(
                "No se pudieron sincronizar fotos nuevas:",
                describir_error_supabase(error),
            )

    personas = (
        cliente.table("people")
        .select("id,name")
        .eq("active", True)
        .execute()
        .data
    )
    filas_embeddings = (
        cliente.table("face_embeddings")
        .select("person_id,embedding")
        .execute()
        .data
    )
    nombres_por_id = {
        persona["id"]: persona["name"]
        for persona in personas
    }
    autorizadas = []

    for fila in filas_embeddings:
        persona_id = fila["person_id"]
        if persona_id not in nombres_por_id:
            continue

        embedding = np.asarray(
            fila["embedding"],
            dtype=np.float32,
        ).reshape(1, -1)
        if embedding.size != 128 or not np.isfinite(embedding).all():
            print("Embedding inválido para:", nombres_por_id[persona_id])
            continue

        autorizadas.append(
            {
                "id": persona_id,
                "name": nombres_por_id[persona_id],
                "embedding": embedding,
            }
        )

    autorizadas.sort(key=lambda persona: str(persona["id"]))
    return autorizadas


def galeria_supabase_worker(config, sincronizacion):
    """Reintenta Supabase siempre, conservando la última galería válida."""

    config_supabase = config.get("supabase", {})
    intervalo_reintento = float(
        config_supabase.get("retry_seconds", 10)
    )
    intervalo_galeria = float(
        config_supabase.get("gallery_refresh_seconds", 5)
    )
    intervalo_fotos = float(
        config_supabase.get("face_sync_seconds", 60)
    )
    cliente = None
    ultimo_intento_fotos = 0.0
    error_anterior = None

    try:
        reconocedor = cv2.FaceRecognizerSF.create(
            str(RUTA_MODELO),
            "",
        )
    except Exception as error:
        print("No se pudo iniciar la sincronización facial:", error)
        return

    while not sincronizacion.shutdown.is_set():
        ahora = time.monotonic()
        sincronizar_fotos = (
            ahora - ultimo_intento_fotos >= intervalo_fotos
        )

        if sincronizar_fotos:
            ultimo_intento_fotos = ahora

        try:
            if cliente is None:
                cliente = crear_cliente_supabase(config)

            personas = cargar_personas_supabase(
                config,
                reconocedor,
                cliente=cliente,
                sincronizar_fotos=sincronizar_fotos,
            )
            anteriores = galeria_compartida.obtener()

            if not galerias_equivalentes(anteriores, personas):
                # El archivo se actualiza antes que la memoria. Si la Pi se
                # apaga, siempre quedará una versión completa y coherente.
                guardar_respaldo_local(personas)
                galeria_compartida.reemplazar(personas)
                print(
                    "Galería facial actualizada:",
                    len(personas),
                    "personas habilitadas",
                )

            if error_anterior is not None:
                print("Conexión con Supabase recuperada")
            error_anterior = None
            espera = intervalo_galeria

        except Exception as error:
            cliente = None
            descripcion = describir_error_supabase(error)
            if descripcion != error_anterior:
                print(
                    "Supabase no disponible; se mantiene la galería local:",
                    descripcion,
                )
            error_anterior = descripcion
            espera = intervalo_reintento

        sincronizacion.shutdown.wait(max(1.0, espera))
