"""Worker encargado de detectar rostros."""

import cv2

from core.buffers import guardar_muestras
from core.states import MensajePipeline


RUTA_MODELO = (
    "app/Tareas/deteccion/"
    "face_detection_yunet_2023mar.onnx"
)


def deteccion_worker(
    config,
    sincronizacion,
    cola_mensajes,
):
    """Captura imágenes y busca un rostro."""

    camera_config = config["camera"]
    umbral_deteccion = config["thresholds"]["detection"]

    ancho = camera_config["width"]
    alto = camera_config["height"]
    indice_camara = camera_config["index"]

    # ========================================================
    # CONFIGURAR CÁMARA
    # ========================================================

    camara = cv2.VideoCapture(indice_camara)

    camara.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
    camara.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)

    if not camara.isOpened():
        cola_mensajes.put(MensajePipeline.ERROR)
        return

    # ========================================================
    # CARGAR MODELO DE DETECCIÓN
    # ========================================================

    detector = cv2.FaceDetectorYN.create(
        RUTA_MODELO,
        "",
        (ancho, alto),
        umbral_deteccion,
        0.3,
        5000,
    )

    # ========================================================
    # BUSCAR ROSTROS
    # ========================================================

    while not sincronizacion.shutdown.is_set():

        # Esperar hasta que el pipeline habilite la detección
        sincronizacion.detection_enabled.wait()

        if sincronizacion.shutdown.is_set():
            break

        # Modelo 1 comienza a trabajar
        sincronizacion.model1_idle.clear()

        lectura_correcta, imagen = camara.read()

        if not lectura_correcta:
            sincronizacion.model1_idle.set()
            cola_mensajes.put(MensajePipeline.ERROR)
            break

        detector.setInputSize(
            (imagen.shape[1], imagen.shape[0])
        )

        resultado, rostros = detector.detect(imagen)

        if rostros is not None:

            # Utilizar el primer rostro detectado
            rostro_detectado = rostros[0]

            x = int(rostro_detectado[0])
            y = int(rostro_detectado[1])
            ancho_rostro = int(rostro_detectado[2])
            alto_rostro = int(rostro_detectado[3])

            # Evitar posiciones fuera de la imagen
            x = max(0, x)
            y = max(0, y)

            fin_x = min(
                imagen.shape[1],
                x + ancho_rostro,
            )

            fin_y = min(
                imagen.shape[0],
                y + alto_rostro,
            )

            rostro = imagen[y:fin_y, x:fin_x].copy()

            if rostro.size > 0:

                # Bloquear nuevas detecciones
                sincronizacion.detection_enabled.clear()

                # Guardar una copia para cada modelo
                guardar_muestras(
                    rostro.copy(),
                    (
                        imagen.copy(),
                        rostro_detectado.copy(),
                    ),
                )

                # Avisar que Buffer 1 está preparado
                sincronizacion.buffer1_ready.set()

                # Avisar al Pipeline Manager
                cola_mensajes.put(
                    MensajePipeline.CANDIDATO_DETECTADO
                )

        # Modelo 1 vuelve a un punto seguro
        sincronizacion.model1_idle.set()

    camara.release()