"""Vista local de la cámara sin abrir un segundo dispositivo."""

from threading import Lock

import cv2

from core.states import MensajePipeline


class VistaCamaraCompartida:
    """Comparte el último frame capturado con el hilo de la interfaz."""

    def __init__(self):
        self._lock = Lock()
        self._imagen = None
        self._version = 0

    def actualizar(self, imagen):
        """Publica una referencia a una imagen que ya no será modificada."""

        with self._lock:
            self._imagen = imagen
            self._version += 1

    def obtener_si_cambio(self, version_anterior):
        """Devuelve solamente los frames que todavía no fueron mostrados."""

        with self._lock:
            if self._version == version_anterior:
                return version_anterior, None
            return self._version, self._imagen


def ejecutar_vista_camara(
    vista,
    sincronizacion,
    cola_mensajes,
    config,
):
    """Mantiene la ventana en el hilo principal de la aplicación."""

    nombre = str(config.get("window_name", "SmartGate"))
    ancho = int(config.get("width", 960))
    alto = int(config.get("height", 720))
    demora_tecla = max(1, int(config.get("wait_key_ms", 30)))

    try:
        cv2.namedWindow(nombre, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(nombre, ancho, alto)
    except cv2.error as error:
        print(
            "No se pudo abrir la ventana de cámara; "
            "SmartGate continuará sin vista local:",
            error,
        )
        return

    print("Vista de cámara activa. Presioná Q o Esc para cerrar SmartGate.")
    version = -1

    try:
        while not sincronizacion.shutdown.is_set():
            version, imagen = vista.obtener_si_cambio(version)

            if imagen is not None:
                cv2.imshow(nombre, imagen)

            tecla = cv2.waitKey(demora_tecla) & 0xFF
            if tecla in (ord("q"), ord("Q"), 27):
                cola_mensajes.put(MensajePipeline.APAGAR)
                break

            try:
                ventana_visible = cv2.getWindowProperty(
                    nombre,
                    cv2.WND_PROP_VISIBLE,
                )
            except cv2.error:
                ventana_visible = 1

            if ventana_visible < 1:
                cola_mensajes.put(MensajePipeline.APAGAR)
                break

    except cv2.error as error:
        print(
            "La ventana de cámara dejó de estar disponible; "
            "SmartGate continuará funcionando:",
            error,
        )

    finally:
        try:
            cv2.destroyWindow(nombre)
        except cv2.error:
            pass
