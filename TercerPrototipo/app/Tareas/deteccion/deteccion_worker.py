"""Worker encargado de detectar rostros."""

import cv2

from core.buffers import guardar_muestras
from core.camara import crear_camara
from core.states import MensajePipeline


RUTA_MODELO = (
    "app/Tareas/deteccion/"
    "face_detection_yunet_2023mar.onnx"
)

ESCALA_ANTISPOOF = 2.7


def deteccion_worker(
    config,
    sincronizacion,
    cola_mensajes,
    vista_camara=None,
):
    """Captura imágenes y busca un rostro."""

    camera_config = config["camera"]
    umbral_deteccion = config["thresholds"]["detection"]

    ancho = camera_config["width"]
    alto = camera_config["height"]
    # Picamera2 permite usar la OV5647 conectada al puerto CSI. La
    # interfaz devuelta conserva read/release para no modificar el
    # resto del pipeline.
    try:
        camara = crear_camara(camera_config)
    except Exception as error:
        print("No se pudo iniciar la cámara:", error)
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    if not camara.isOpened():
        print("No se pudo abrir la cámara")
        camara.release()
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    # Cargar el modelo
    try:
        detector = cv2.FaceDetectorYN.create(
            RUTA_MODELO,
            "",
            (ancho, alto),
            umbral_deteccion,
            0.3,
            5000,
        )

    except Exception as error:
        print("No se pudo cargar el modelo de detección:", error)
        camara.release()
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    while not sincronizacion.shutdown.is_set():
        try:
            lectura_correcta, imagen = camara.read()

            if not lectura_correcta:
                raise RuntimeError(
                    "No se pudo obtener una imagen de la cámara"
                )

            # La misma captura alimenta la ventana y el detector. La cámara
            # nunca se abre dos veces y la vista continúa aunque el pipeline
            # esté esperando que el portón cierre.
            if vista_camara is not None:
                vista_camara.actualizar(imagen)

            if not sincronizacion.detection_enabled.is_set():
                continue

            sincronizacion.model1_idle.clear()

            # Evita comenzar una inferencia si el pipeline retiró el permiso
            # entre la comprobación anterior y la marca de modelo ocupado.
            if not sincronizacion.detection_enabled.is_set():
                continue

            detector.setInputSize(
                (imagen.shape[1], imagen.shape[0])
            )

            resultado, rostros = detector.detect(imagen)

            if rostros is None:
                if vista_camara is not None:
                    vista_camara.actualizar_deteccion()
                continue

            rostro_detectado = rostros[0]

            # YuNet entrega la confianza de detección en el último
            # valor del rostro detectado.
            sincronizacion.detection_score = float(
                rostro_detectado[-1]
            )
            sincronizacion.antispoof_score = None

            if vista_camara is not None:
                vista_camara.actualizar_deteccion(
                    rostro_detectado,
                    sincronizacion.detection_score,
                )

            x = int(rostro_detectado[0])
            y = int(rostro_detectado[1])

            ancho_rostro = int(rostro_detectado[2])
            alto_rostro = int(rostro_detectado[3])

            # Calcular el centro del rostro
            centro_x = x + ancho_rostro / 2
            centro_y = y + alto_rostro / 2

            # Ampliar el recorte para antispoofing
            ancho_recorte = ancho_rostro * ESCALA_ANTISPOOF
            alto_recorte = alto_rostro * ESCALA_ANTISPOOF

            inicio_x = max(
                0,
                int(centro_x - ancho_recorte / 2),
            )

            inicio_y = max(
                0,
                int(centro_y - alto_recorte / 2),
            )

            fin_x = min(
                imagen.shape[1],
                int(centro_x + ancho_recorte / 2),
            )

            fin_y = min(
                imagen.shape[0],
                int(centro_y + alto_recorte / 2),
            )

            rostro = imagen[
                inicio_y:fin_y,
                inicio_x:fin_x,
            ].copy()

            if rostro.size == 0:
                continue

            # Impedir que se acepte otro candidato
            sincronizacion.detection_enabled.clear()

            guardar_muestras(
                rostro.copy(),
                (
                    imagen.copy(),
                    rostro_detectado.copy(),
                ),
            )

            # Avisar al pipeline antes de iniciar antispoofing
            cola_mensajes.put(
                MensajePipeline.CANDIDATO_DETECTADO
            )

            sincronizacion.buffer1_ready.set()

        except Exception as error:
            sincronizacion.detection_enabled.clear()

            print("Error durante la detección:", error)

            cola_mensajes.put(
                MensajePipeline.ERROR
            )

        finally:
            # Modelo 1 siempre vuelve a un punto seguro
            sincronizacion.model1_idle.set()

    camara.release()
