"""Worker encargado del reconocimiento facial."""

import time
from pathlib import Path

import cv2
import numpy as np
from dotenv import dotenv_values
from supabase import create_client

from core.buffers import tomar_buffer2
from core.states import MensajePipeline, ResultadoPipeline
from Tareas.supabase.rostros_sync import (
    sincronizar_rostros_supabase,
)


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]

RUTA_MODELO = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "reconocimiento"
    / "face_recognition_sface_2021dec.onnx"
)

RUTA_EMBEDDINGS_LOCAL = (
    CARPETA_PROYECTO
    / "data"
    / "embeddings.npy"
)

RUTA_ENV = CARPETA_PROYECTO / "app" / ".env"

# Activar o desactivar una persona debe reflejarse casi de inmediato.
INTERVALO_ACTUALIZACION_ACCESOS = 2

# Las fotos requieren detección y generación de embeddings, una tarea
# más costosa que consultar el estado activo de las personas.
INTERVALO_SINCRONIZACION_ROSTROS = 60


def crear_cliente_supabase():
    """Crea una sesión autenticada reutilizable con Supabase."""

    credenciales = dotenv_values(RUTA_ENV)

    variables = (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_DEVICE_EMAIL",
        "SUPABASE_DEVICE_PASSWORD",
    )
    faltantes = [
        nombre
        for nombre in variables
        if not credenciales.get(nombre)
    ]
    if faltantes:
        raise RuntimeError(
            "Faltan variables en app/.env: "
            + ", ".join(faltantes)
        )

    cliente = create_client(
        credenciales["SUPABASE_URL"],
        credenciales["SUPABASE_PUBLISHABLE_KEY"],
    )
    cliente.auth.sign_in_with_password(
        {
            "email": credenciales["SUPABASE_DEVICE_EMAIL"],
            "password": credenciales["SUPABASE_DEVICE_PASSWORD"],
        }
    )

    return cliente


def cargar_personas_supabase(
    config,
    reconocedor,
    cliente=None,
    sincronizar_fotos=True,
):
    """Descarga las personas activas y sus embeddings."""

    if cliente is None:
        cliente = crear_cliente_supabase()

    # Procesar las fotos nuevas del panel antes de cargar
    # la galería que utilizará el reconocimiento.
    if sincronizar_fotos:
        try:
            sincronizar_rostros_supabase(
                cliente,
                config,
                reconocedor,
            )
        except Exception as error:
            # Una falla de Storage no debe impedir utilizar los
            # embeddings que ya estaban guardados en la base.
            print(
                "No se pudieron sincronizar las fotos:",
                error,
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
    personas_autorizadas = []

    for fila in filas_embeddings:
        persona_id = fila["person_id"]
        if persona_id not in nombres_por_id:
            continue

        embedding = np.asarray(
            fila["embedding"],
            dtype=np.float32,
        ).reshape(1, -1)

        if embedding.size != 128:
            print(
                "Embedding invalido para:",
                nombres_por_id[persona_id],
            )
            continue

        personas_autorizadas.append(
            {
                "id": persona_id,
                "name": nombres_por_id[persona_id],
                "embedding": embedding,
            }
        )

    return personas_autorizadas


def guardar_respaldo_local(personas_autorizadas):
    """Actualiza el respaldo para poder reconocer sin internet."""

    if not personas_autorizadas:
        # Un respaldo viejo no debe volver a autorizar a alguien que
        # fue desactivado desde el panel.
        if RUTA_EMBEDDINGS_LOCAL.exists():
            RUTA_EMBEDDINGS_LOCAL.unlink()
        return

    embeddings = np.vstack(
        [
            persona["embedding"]
            for persona in personas_autorizadas
        ]
    ).astype(np.float32)
    RUTA_EMBEDDINGS_LOCAL.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    np.save(RUTA_EMBEDDINGS_LOCAL, embeddings)


def cargar_respaldo_local():
    """Carga embeddings.npy cuando Supabase no esta disponible."""
    if not RUTA_EMBEDDINGS_LOCAL.exists():
        print(
            "No existe respaldo facial local; "
            "todos los accesos quedarán denegados"
        )
        return []

    embeddings = np.load(RUTA_EMBEDDINGS_LOCAL)
    return [
        {
            "id": None,
            "name": f"Usuario local {indice + 1}",
            "embedding": embedding
            .reshape(1, -1)
            .astype(np.float32),
        }
        for indice, embedding in enumerate(embeddings)
    ]


def reconocimiento_worker(
    config,
    sincronizacion,
    cola_mensajes,
):
    """Compara el rostro con las personas autorizadas."""
    umbral_reconocimiento = (
        config["thresholds"]["recognition"]
    )
    cliente_supabase = None

    try:
        reconocedor = cv2.FaceRecognizerSF.create(
            str(RUTA_MODELO),
            "",
        )

        try:
            cliente_supabase = crear_cliente_supabase()
            personas_autorizadas = (
                cargar_personas_supabase(
                    config,
                    reconocedor,
                    cliente=cliente_supabase,
                )
            )
            guardar_respaldo_local(
                personas_autorizadas
            )
            print(
                "Personas cargadas desde Supabase:",
                len(personas_autorizadas),
            )
        except Exception as error:
            cliente_supabase = None
            print(
                "No se pudo consultar Supabase:",
                error,
            )
            print("Utilizando respaldo local")
            personas_autorizadas = (
                cargar_respaldo_local()
            )

    except Exception as error:
        print(
            "No se pudo iniciar el reconocimiento:",
            error,
        )
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    ahora = time.monotonic()
    ultima_actualizacion_accesos = ahora
    ultima_sincronizacion_rostros = ahora

    while not sincronizacion.shutdown.is_set():
        rostro_disponible = (
            sincronizacion.recognition_ready.wait(
                timeout=1
            )
        )

        if sincronizacion.shutdown.is_set():
            break

        ahora = time.monotonic()

        debe_actualizar_accesos = (
            ahora - ultima_actualizacion_accesos
            >= INTERVALO_ACTUALIZACION_ACCESOS
        )
        debe_sincronizar_rostros = (
            ahora - ultima_sincronizacion_rostros
            >= INTERVALO_SINCRONIZACION_ROSTROS
        )

        if (
            debe_actualizar_accesos
            or debe_sincronizar_rostros
        ):
            # El estado active se consulta cada pocos segundos. Las
            # fotos se procesan con menor frecuencia porque requieren
            # ejecutar los modelos de detección y reconocimiento.
            ultima_actualizacion_accesos = ahora

            if debe_sincronizar_rostros:
                ultima_sincronizacion_rostros = ahora

            try:
                if cliente_supabase is None:
                    cliente_supabase = (
                        crear_cliente_supabase()
                    )

                personas_actualizadas = (
                    cargar_personas_supabase(
                        config,
                        reconocedor,
                        cliente=cliente_supabase,
                        sincronizar_fotos=(
                            debe_sincronizar_rostros
                        ),
                    )
                )

                accesos_anteriores = {
                    (persona["id"], persona["name"])
                    for persona in personas_autorizadas
                }
                accesos_actuales = {
                    (persona["id"], persona["name"])
                    for persona in personas_actualizadas
                }

                personas_autorizadas = personas_actualizadas
                guardar_respaldo_local(
                    personas_autorizadas
                )

                if accesos_actuales != accesos_anteriores:
                    print(
                        "Accesos actualizados desde Supabase:",
                        len(personas_autorizadas),
                        "embeddings activos",
                    )

            except Exception as error:
                # Conservar la lista que ya está en memoria si una
                # sincronización periódica falla.
                cliente_supabase = None
                print(
                    "No se pudo actualizar la galería facial:",
                    error,
                )

        if not rostro_disponible:
            continue

        sincronizacion.model3_idle.clear()

        try:
            imagen, rostro_detectado = tomar_buffer2()
            sincronizacion.recognition_ready.clear()

            rostro_alineado = reconocedor.alignCrop(
                imagen,
                rostro_detectado,
            )
            embedding_actual = reconocedor.feature(
                rostro_alineado
            )

            mejor_persona = None
            mejor_similitud = None

            for persona in personas_autorizadas:
                similitud = reconocedor.match(
                    embedding_actual,
                    persona["embedding"],
                    cv2.FaceRecognizerSF_FR_COSINE,
                )

                if (
                    mejor_similitud is None
                    or similitud > mejor_similitud
                ):
                    mejor_similitud = similitud
                    mejor_persona = persona

            if (
                mejor_persona is not None
                and mejor_similitud is not None
                and mejor_similitud
                >= umbral_reconocimiento
            ):
                print(
                    "Identidad autorizada:",
                    mejor_persona["name"],
                    "- similitud:",
                    f"{mejor_similitud * 100:.1f}%",
                )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_AUTORIZADA
                        ),
                        persona_id=mejor_persona["id"],
                        similitud=float(mejor_similitud),
                        antispoof=(
                            sincronizacion.antispoof_score
                        ),
                        deteccion=(
                            sincronizacion.detection_score
                        ),
                    )
                )
            else:
                if mejor_similitud is None:
                    print(
                        "Identidad rechazada: "
                        "no hay embeddings activos"
                    )
                else:
                    print(
                        "Identidad rechazada - similitud:",
                        f"{mejor_similitud * 100:.1f}%",
                    )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_RECHAZADA
                        ),
                        similitud=(
                            float(mejor_similitud)
                            if mejor_similitud is not None
                            else None
                        ),
                        antispoof=(
                            sincronizacion.antispoof_score
                        ),
                        deteccion=(
                            sincronizacion.detection_score
                        ),
                    )
                )

        except Exception as error:
            sincronizacion.recognition_ready.clear()
            print(
                "Error durante el reconocimiento:",
                error,
            )
            cola_mensajes.put(MensajePipeline.ERROR)

        finally:
            sincronizacion.model3_idle.set()
