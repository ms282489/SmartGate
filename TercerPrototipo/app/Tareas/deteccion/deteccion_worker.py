"""Worker encargado de detectar rostros."""

import time
from pathlib import Path

import cv2

from core.buffers import guardar_muestras
from core.camara import crear_camara
from core.metricas import ahora as reloj, medidor
from core.states import MensajePipeline


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_MODELO = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "deteccion"
    / "face_detection_yunet_2023mar.onnx"
)

ESCALA_ANTISPOOF = 2.7


class ControlCadenciaDeteccion:
    """Reduce inferencias cuando lleva varios segundos sin ver rostros."""

    def __init__(
        self,
        segundos_sin_rostro,
        intervalo_activo,
        intervalo_descanso,
    ):
        self.segundos_sin_rostro = max(
            0.0,
            float(segundos_sin_rostro),
        )
        self.intervalo_activo = max(
            0.0,
            float(intervalo_activo),
        )
        self.intervalo_descanso = max(
            0.01,
            float(intervalo_descanso),
        )
        self.en_descanso = False
        self._sin_rostro_desde = None
        self._proxima_inferencia = 0.0

    def reiniciar(self, ahora):
        """Comienza una búsqueda rápida nueva."""

        self.en_descanso = False
        self._sin_rostro_desde = float(ahora)
        self._proxima_inferencia = float(ahora)

    def debe_procesar(self, ahora):
        """Indica si corresponde ejecutar YuNet sobre el cuadro actual."""

        ahora = float(ahora)
        if ahora < self._proxima_inferencia:
            return False

        intervalo = (
            self.intervalo_descanso
            if self.en_descanso
            else self.intervalo_activo
        )
        self._proxima_inferencia = ahora + intervalo
        return True

    def registrar_sin_rostro(self, ahora):
        """Activa el sondeo de descanso al vencer el tiempo configurado."""

        ahora = float(ahora)
        if self._sin_rostro_desde is None:
            self._sin_rostro_desde = ahora

        if (
            not self.en_descanso
            and ahora - self._sin_rostro_desde
            >= self.segundos_sin_rostro
        ):
            self.en_descanso = True
            self._proxima_inferencia = (
                ahora + self.intervalo_descanso
            )

    def registrar_rostro(self, ahora):
        """Vuelve a la cadencia rápida al encontrar una cara."""

        self.reiniciar(ahora)


def escalar_deteccion(rostro, escala_x, escala_y):
    """Lleva caja y landmarks de YuNet a la imagen de resolución completa."""

    rostro_escalado = rostro.copy()

    # Caja: x, y, ancho y alto.
    rostro_escalado[0] *= escala_x
    rostro_escalado[1] *= escala_y
    rostro_escalado[2] *= escala_x
    rostro_escalado[3] *= escala_y

    # YuNet entrega cinco landmarks como pares x/y antes del puntaje final.
    for indice in range(4, len(rostro_escalado) - 1, 2):
        rostro_escalado[indice] *= escala_x
        rostro_escalado[indice + 1] *= escala_y

    return rostro_escalado


def deteccion_worker(
    config,
    sincronizacion,
    cola_mensajes,
    vista_camara=None,
):
    """Captura imágenes y busca un rostro."""

    camera_config = config["camera"]
    detection_config = config.get("detection", {})
    umbral_deteccion = config["thresholds"]["detection"]

    ancho = camera_config["width"]
    alto = camera_config["height"]
    ancho_inferencia = min(
        ancho,
        max(
            1,
            int(detection_config.get("inference_width", 640)),
        ),
    )
    alto_inferencia = min(
        alto,
        max(
            1,
            int(detection_config.get("inference_height", 480)),
        ),
    )
    control_cadencia = ControlCadenciaDeteccion(
        segundos_sin_rostro=detection_config.get(
            "no_face_idle_seconds",
            5.0,
        ),
        intervalo_activo=detection_config.get(
            "active_scan_interval_seconds",
            0.0,
        ),
        intervalo_descanso=detection_config.get(
            "idle_scan_interval_seconds",
            0.2,
        ),
    )
    deteccion_estaba_habilitada = False
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
            str(RUTA_MODELO),
            "",
            (ancho_inferencia, alto_inferencia),
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
            t_captura = reloj()

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
                deteccion_estaba_habilitada = False
                continue

            ahora = time.monotonic()
            if not deteccion_estaba_habilitada:
                control_cadencia.reiniciar(ahora)
                deteccion_estaba_habilitada = True

            if not control_cadencia.debe_procesar(ahora):
                continue

            sincronizacion.model1_idle.clear()

            # Evita comenzar una inferencia si el pipeline retiró el permiso
            # entre la comprobación anterior y la marca de modelo ocupado.
            if not sincronizacion.detection_enabled.is_set():
                continue

            if (
                imagen.shape[1] != ancho_inferencia
                or imagen.shape[0] != alto_inferencia
            ):
                imagen_detector = cv2.resize(
                    imagen,
                    (ancho_inferencia, alto_inferencia),
                    interpolation=cv2.INTER_AREA,
                )
            else:
                imagen_detector = imagen

            detector.setInputSize(
                (
                    imagen_detector.shape[1],
                    imagen_detector.shape[0],
                )
            )

            t_deteccion_inicio = reloj()
            resultado, rostros = detector.detect(imagen_detector)
            t_deteccion_fin = reloj()
            medidor.registrar_deteccion(
                t_deteccion_fin - t_deteccion_inicio,
                rostros is not None and len(rostros) > 0,
                control_cadencia.en_descanso,
            )

            if rostros is None or len(rostros) == 0:
                control_cadencia.registrar_sin_rostro(
                    time.monotonic()
                )
                if vista_camara is not None:
                    vista_camara.actualizar_deteccion(
                        descanso=control_cadencia.en_descanso,
                    )
                continue

            control_cadencia.registrar_rostro(time.monotonic())

            rostro_detectado = escalar_deteccion(
                rostros[0],
                imagen.shape[1] / imagen_detector.shape[1],
                imagen.shape[0] / imagen_detector.shape[0],
            )

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

            # Las marcas se registran antes de despertar al antispoofing para
            # que el intento ya exista cuando Modelo 2 anote las suyas.
            medidor.nuevo_intento(
                {
                    "captura": t_captura,
                    "deteccion_inicio": t_deteccion_inicio,
                    "deteccion_fin": t_deteccion_fin,
                    "muestras_listas": reloj(),
                }
            )
            medidor.anotar(
                puntaje_deteccion=sincronizacion.detection_score,
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
