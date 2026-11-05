"""Vista local de la cámara sin abrir un segundo dispositivo."""

from threading import Lock

import cv2

from core.states import MensajePipeline


COLOR_NEUTRO = (210, 210, 210)
COLOR_ESPERA = (0, 255, 255)
COLOR_CONECTADO = (0, 255, 0)
COLOR_DESCONECTADO = (0, 165, 255)
COLOR_APROBADO = (0, 255, 0)
COLOR_RECHAZADO = (0, 0, 255)


class VistaCamaraCompartida:
    """Comparte el frame y los resultados de todos los modelos."""

    def __init__(self):
        self._lock = Lock()
        self._imagen = None
        self._rostro = None
        self._estado_supabase = "SUPABASE: CARGANDO CACHE LOCAL"
        self._color_supabase = COLOR_ESPERA
        self._estado_deteccion = "DETECCION: SIN ROSTRO"
        self._color_deteccion = COLOR_NEUTRO
        self._estado_antispoof = "ANTISPOOF: NO EVALUADO"
        self._color_antispoof = COLOR_NEUTRO
        self._estado_reconocimiento = "RECONOCIMIENTO: NO EVALUADO"
        self._color_reconocimiento = COLOR_NEUTRO
        self._resultado_final = "RESULTADO: ESPERANDO"
        self._color_resultado = COLOR_ESPERA
        self._version = 0

    def actualizar(self, imagen):
        """Publica una referencia a una imagen que ya no será modificada."""

        with self._lock:
            self._imagen = imagen
            self._version += 1

    def actualizar_supabase(self, conectado, cantidad):
        """Muestra si la galería proviene de Supabase o de la caché."""

        cantidad = int(cantidad)
        with self._lock:
            if conectado:
                self._estado_supabase = (
                    f"SUPABASE: CONECTADO - {cantidad} EMBEDDINGS"
                )
                self._color_supabase = COLOR_CONECTADO
            else:
                self._estado_supabase = (
                    "SUPABASE: SIN CONEXION - "
                    f"CACHE: {cantidad} EMBEDDINGS"
                )
                self._color_supabase = COLOR_DESCONECTADO
            self._version += 1

    def actualizar_deteccion(self, rostro=None, puntaje=None):
        """Actualiza el rectángulo y el puntaje del detector YuNet."""

        with self._lock:
            if rostro is None:
                self._rostro = None
                self._estado_deteccion = "DETECCION: SIN ROSTRO"
                self._color_deteccion = COLOR_NEUTRO
            else:
                self._rostro = tuple(int(valor) for valor in rostro[:4])
                self._estado_deteccion = (
                    f"DETECCION: APROBADA {float(puntaje):.2f}"
                )
                self._color_deteccion = COLOR_APROBADO
            self._version += 1

    def actualizar_antispoof(self, puntaje, aprobado):
        """Publica el resultado del modelo de prueba de vida."""

        with self._lock:
            estado = "APROBADO" if aprobado else "RECHAZADO"
            self._estado_antispoof = (
                f"ANTISPOOF: {estado} {float(puntaje):.2f}"
            )
            self._color_antispoof = (
                COLOR_APROBADO if aprobado else COLOR_RECHAZADO
            )
            self._version += 1

    def actualizar_reconocimiento(
        self,
        nombre,
        similitud,
        aprobado,
    ):
        """Publica nombre y similitud calculados por SFace."""

        with self._lock:
            if similitud is None:
                self._estado_reconocimiento = (
                    "RECONOCIMIENTO: SIN EMBEDDINGS ACTIVOS"
                )
            elif aprobado:
                self._estado_reconocimiento = (
                    f"RECONOCIMIENTO: {nombre} "
                    f"{float(similitud) * 100:.1f}%"
                )
            else:
                self._estado_reconocimiento = (
                    "RECONOCIMIENTO: RECHAZADO "
                    f"{float(similitud) * 100:.1f}%"
                )
            self._color_reconocimiento = (
                COLOR_APROBADO if aprobado else COLOR_RECHAZADO
            )
            self._version += 1

    def actualizar_estado(self, texto, color):
        """Actualiza el resultado final; mantiene compatibilidad interna."""

        with self._lock:
            self._resultado_final = str(texto)
            self._color_resultado = tuple(color)
            self._version += 1

    def preparar_busqueda(self):
        """Limpia los resultados anteriores antes del siguiente rostro."""

        with self._lock:
            self._rostro = None
            self._estado_deteccion = "DETECCION: SIN ROSTRO"
            self._color_deteccion = COLOR_NEUTRO
            self._estado_antispoof = "ANTISPOOF: NO EVALUADO"
            self._color_antispoof = COLOR_NEUTRO
            self._estado_reconocimiento = "RECONOCIMIENTO: NO EVALUADO"
            self._color_reconocimiento = COLOR_NEUTRO
            self._resultado_final = "RESULTADO: ESPERANDO"
            self._color_resultado = COLOR_ESPERA
            self._version += 1

    def obtener_si_cambio(self, version_anterior):
        """Devuelve una instantánea coherente solamente si hubo cambios."""

        with self._lock:
            if self._version == version_anterior:
                return version_anterior, None, None

            estados = (
                (self._estado_supabase, self._color_supabase),
                (self._estado_deteccion, self._color_deteccion),
                (self._estado_antispoof, self._color_antispoof),
                (
                    self._estado_reconocimiento,
                    self._color_reconocimiento,
                ),
                (self._resultado_final, self._color_resultado),
            )
            datos = {
                "rostro": self._rostro,
                "estados": estados,
                "color_resultado": self._color_resultado,
            }
            return self._version, self._imagen, datos


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
            version, imagen, datos = vista.obtener_si_cambio(version)

            if imagen is not None:
                imagen_visible = imagen.copy()
                rostro = datos["rostro"]

                if rostro is not None:
                    x, y, ancho_rostro, alto_rostro = rostro
                    cv2.rectangle(
                        imagen_visible,
                        (max(0, x), max(0, y)),
                        (
                            min(imagen_visible.shape[1], x + ancho_rostro),
                            min(imagen_visible.shape[0], y + alto_rostro),
                        ),
                        datos["color_resultado"],
                        2,
                    )

                # Panel semitransparente para conservar el video visible y
                # mostrar, como en probar_camara.py, cada etapa por separado.
                panel = imagen_visible.copy()
                alto_panel = min(imagen_visible.shape[0], 170)
                cv2.rectangle(
                    panel,
                    (0, 0),
                    (imagen_visible.shape[1], alto_panel),
                    (0, 0, 0),
                    -1,
                )
                cv2.addWeighted(
                    panel,
                    0.62,
                    imagen_visible,
                    0.38,
                    0,
                    imagen_visible,
                )

                for posicion, (texto, color) in enumerate(datos["estados"]):
                    cv2.putText(
                        imagen_visible,
                        texto,
                        (20, 28 + posicion * 31),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.62,
                        color,
                        2,
                        cv2.LINE_AA,
                    )

                cv2.imshow(nombre, imagen_visible)

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
