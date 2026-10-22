"""Acceso uniforme a la cámara utilizada por SmartGate."""

import time


class CamaraPicamera2:
    """Adapta Picamera2 a la interfaz simple usada por el pipeline."""

    def __init__(self, config):
        try:
            from picamera2 import Picamera2
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "Picamera2 no está instalado. Consultá "
                "INSTALACION_RASPBERRY.md"
            ) from error

        indice = int(config.get("index", 0))
        ancho = int(config["width"])
        alto = int(config["height"])
        fps = float(config.get("fps", 20))
        calentamiento = float(
            config.get("warmup_seconds", 2.0)
        )

        camara = Picamera2(indice)

        try:
            configuracion = camara.create_video_configuration(
                main={
                    "size": (ancho, alto),
                    # Aunque el nombre parezca invertido, Picamera2
                    # entrega RGB888 como BGR, el orden que usa OpenCV.
                    "format": "RGB888",
                },
                controls={"FrameRate": fps},
                buffer_count=4,
            )
            camara.configure(configuracion)
            camara.start()
            time.sleep(calentamiento)

        except Exception:
            camara.close()
            raise

        self._camara = camara

    def isOpened(self):
        """Indica si la cámara fue inicializada correctamente."""

        return self._camara is not None

    def read(self):
        """Devuelve una imagen BGR con la misma forma que OpenCV."""

        if self._camara is None:
            return False, None

        try:
            imagen = self._camara.capture_array("main")
        except Exception:
            return False, None

        if imagen is None or imagen.size == 0:
            return False, None

        return True, imagen

    def release(self):
        """Detiene la cámara y libera libcamera."""

        camara = self._camara
        self._camara = None

        if camara is None:
            return

        try:
            camara.stop()
        finally:
            camara.close()


class CamaraOpenCV:
    """Alternativa para realizar pruebas con una cámara USB."""

    def __init__(self, config):
        import cv2

        self._camara = cv2.VideoCapture(
            int(config.get("index", 0))
        )
        self._camara.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            int(config["width"]),
        )
        self._camara.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            int(config["height"]),
        )

    def isOpened(self):
        return self._camara.isOpened()

    def read(self):
        return self._camara.read()

    def release(self):
        self._camara.release()


def crear_camara(config):
    """Crea el backend indicado en la sección camera del YAML."""

    backend = str(
        config.get("backend", "picamera2")
    ).lower()

    if backend == "picamera2":
        return CamaraPicamera2(config)

    if backend == "opencv":
        return CamaraOpenCV(config)

    raise ValueError(
        "Backend de cámara desconocido: "
        f"{backend}. Usá 'picamera2' u 'opencv'."
    )
