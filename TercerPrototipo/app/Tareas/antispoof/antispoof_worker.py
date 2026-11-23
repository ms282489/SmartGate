"""Worker encargado de detectar intentos de engaño."""

from pathlib import Path

import cv2
import numpy as np

from core.buffers import tomar_buffer1
from core.buffers import tomar_buffer2
from core.metricas import medidor
from core.states import MensajePipeline, ResultadoPipeline


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_MODELO = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "antispoof"
    / "MiniFASNetV2.onnx"
)


def antispoof_worker(
    config,
    sincronizacion,
    cola_mensajes,
    vista_camara=None,
):
    """Comprueba si el rostro detectado pertenece a una persona real."""

    umbral_antispoof = config["thresholds"]["antispoof"]

    # Cargar el modelo
    try:
        modelo = cv2.dnn.readNetFromONNX(str(RUTA_MODELO))

    except Exception as error:
        print("No se pudo cargar el modelo antispoofing:", error)
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    while not sincronizacion.shutdown.is_set():

        # Esperar una muestra del modelo de detección
        sincronizacion.buffer1_ready.wait()

        if sincronizacion.shutdown.is_set():
            break

        # Modelo 2 comienza a trabajar
        sincronizacion.model2_idle.clear()

        try:
            # Tomar y vaciar Buffer 1
            rostro = tomar_buffer1()
            medidor.marcar("antispoof_inicio")
            sincronizacion.buffer1_ready.clear()

            # Preparar la imagen para el modelo
            rostro = cv2.resize(rostro, (80, 80))

            entrada = cv2.dnn.blobFromImage(
                rostro,
                scalefactor=1.0,
                size=(80, 80),
                swapRB=False,
                crop=False,
            )

            # Ejecutar el modelo
            medidor.marcar("antispoof_inferencia_inicio")
            modelo.setInput(entrada)
            salida = modelo.forward()[0]
            medidor.marcar("antispoof_inferencia_fin")

            # Convertir la salida en probabilidades
            valores = np.exp(salida - np.max(salida))
            probabilidades = valores / np.sum(valores)

            puntaje_real = float(probabilidades[1])
            sincronizacion.antispoof_score = puntaje_real
            aprobado = puntaje_real >= umbral_antispoof
            medidor.anotar(puntaje_antispoof=puntaje_real)

            if vista_camara is not None:
                vista_camara.actualizar_antispoof(
                    puntaje_real,
                    aprobado,
                )

            # Marcar antes de despertar al reconocimiento o avisar al gestor.
            medidor.marcar("antispoof_fin")

            if aprobado:
                sincronizacion.recognition_ready.set()

            else:
                # Descartar la muestra destinada a reconocimiento
                tomar_buffer2()

                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=MensajePipeline.SPOOF_DETECTADO,
                        antispoof=puntaje_real,
                        deteccion=(
                            sincronizacion.detection_score
                        ),
                    )
                )

        except Exception as error:
            sincronizacion.buffer1_ready.clear()

            print("Error durante el antispoofing:", error)

            cola_mensajes.put(
                MensajePipeline.ERROR
            )

        finally:
            # Modelo 2 siempre vuelve a un punto seguro
            sincronizacion.model2_idle.set()
