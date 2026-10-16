"""Worker encargado del reconocimiento facial."""

from pathlib import Path

import cv2
import numpy as np
from dotenv import dotenv_values
from supabase import create_client

from core.buffers import tomar_buffer2
from core.states import MensajePipeline, ResultadoPipeline


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


def cargar_personas_supabase():
    """Descarga las personas activas y sus embeddings."""
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

    if not personas_autorizadas:
        raise RuntimeError(
            "Supabase no devolvio embeddings autorizados"
        )

    return personas_autorizadas


def guardar_respaldo_local(personas_autorizadas):
    """Actualiza el respaldo para poder reconocer sin internet."""
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
        raise RuntimeError(
            "No existe un respaldo local de embeddings"
        )

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

    try:
        reconocedor = cv2.FaceRecognizerSF.create(
            str(RUTA_MODELO),
            "",
        )

        try:
            personas_autorizadas = (
                cargar_personas_supabase()
            )
            guardar_respaldo_local(
                personas_autorizadas
            )
            print(
                "Personas cargadas desde Supabase:",
                len(personas_autorizadas),
            )
        except Exception as error:
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

    while not sincronizacion.shutdown.is_set():
        sincronizacion.recognition_ready.wait()

        if sincronizacion.shutdown.is_set():
            break

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
            mejor_similitud = -1.0

            for persona in personas_autorizadas:
                similitud = reconocedor.match(
                    embedding_actual,
                    persona["embedding"],
                    cv2.FaceRecognizerSF_FR_COSINE,
                )

                if similitud > mejor_similitud:
                    mejor_similitud = similitud
                    mejor_persona = persona

            if (
                mejor_persona is not None
                and mejor_similitud
                >= umbral_reconocimiento
            ):
                print(
                    "Identidad autorizada:",
                    mejor_persona["name"],
                    "- similitud:",
                    round(mejor_similitud, 3),
                )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_AUTORIZADA
                        ),
                        persona_id=mejor_persona["id"],
                        similitud=float(mejor_similitud),
                    )
                )
            else:
                print(
                    "Identidad rechazada - similitud:",
                    round(mejor_similitud, 3),
                )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_RECHAZADA
                        ),
                        similitud=float(mejor_similitud),
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
