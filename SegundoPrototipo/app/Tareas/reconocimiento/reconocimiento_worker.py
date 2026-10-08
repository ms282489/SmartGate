"""Worker encargado del reconocimiento facial."""

import os

import cv2
import numpy as np

from core.buffers import tomar_buffer2
from core.states import MensajePipeline


RUTA_MODELO = (
    "app/Tareas/reconocimiento/"
    "face_recognition_sface_2021dec.onnx"
)

RUTA_EMBEDDINGS = "data/embeddings.npy"


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
        # Cargar el modelo
        reconocedor = cv2.FaceRecognizerSF.create(
            RUTA_MODELO,
            "",
        )

        # Cargar los rostros autorizados
        if os.path.exists(RUTA_EMBEDDINGS):
            embeddings_autorizados = np.load(
                RUTA_EMBEDDINGS
            )
        else:
            embeddings_autorizados = []

    except Exception as error:
        print("No se pudo iniciar el reconocimiento:", error)
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    while not sincronizacion.shutdown.is_set():

        # Esperar la aprobación del modelo antispoofing
        sincronizacion.recognition_ready.wait()

        if sincronizacion.shutdown.is_set():
            break

        # Modelo 3 comienza a trabajar
        sincronizacion.model3_idle.clear()

        try:
            # Tomar y vaciar Buffer 2
            imagen, rostro_detectado = tomar_buffer2()
            sincronizacion.recognition_ready.clear()

            # Alinear el rostro
            rostro_alineado = reconocedor.alignCrop(
                imagen,
                rostro_detectado,
            )

            # Generar el embedding
            embedding_actual = reconocedor.feature(
                rostro_alineado
            )

            identidad_autorizada = False

            # Comparar con cada persona autorizada
            for embedding_guardado in embeddings_autorizados:

                embedding_guardado = (
                    embedding_guardado
                    .reshape(1, -1)
                    .astype(np.float32)
                )

                similitud = reconocedor.match(
                    embedding_actual,
                    embedding_guardado,
                    cv2.FaceRecognizerSF_FR_COSINE,
                )

                if similitud >= umbral_reconocimiento:
                    identidad_autorizada = True
                    break

            if identidad_autorizada:
                cola_mensajes.put(
                    MensajePipeline.IDENTIDAD_AUTORIZADA
                )

            else:
                cola_mensajes.put(
                    MensajePipeline.IDENTIDAD_RECHAZADA
                )

        except Exception as error:
            sincronizacion.recognition_ready.clear()

            print("Error durante el reconocimiento:", error)

            cola_mensajes.put(
                MensajePipeline.ERROR
            )

        finally:
            # Modelo 3 siempre vuelve a un punto seguro
            sincronizacion.model3_idle.set()
