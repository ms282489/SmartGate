"""Medición de tiempos del pipeline de SmartGate.

Cada intento de acceso atraviesa el pipeline de a uno, por lo que alcanza con
guardar las marcas de tiempo del intento en curso. Los workers anotan hitos
(por ejemplo "fin de la inferencia de YuNet") y, cuando el Pipeline Manager
termina de procesar el resultado, el intento se escribe como una fila en
data/metricas/tiempos_pipeline.csv con la duración de cada etapa y de cada
traspaso entre hilos.

Además, cada inferencia de YuNet (haya o no un rostro) puede registrarse en
data/metricas/tiempos_deteccion.csv para conocer el ritmo real del detector.

La medición está desactivada por defecto (sección `metricas` del YAML). Con la
medición apagada, todas las funciones vuelven inmediatamente.
"""

import csv
import threading
import time
from datetime import datetime
from pathlib import Path


CARPETA_PROYECTO = Path(__file__).resolve().parents[2]

# Hitos de un intento, en el orden en que ocurren.
HITOS = (
    "captura",                       # la cámara entregó el cuadro
    "deteccion_inicio",              # comienza YuNet
    "deteccion_fin",                 # termina YuNet
    "muestras_listas",               # recortes guardados en Buffer 1 y 2
    "antispoof_inicio",              # Modelo 2 tomó Buffer 1
    "antispoof_inferencia_inicio",   # entrada preparada (80x80)
    "antispoof_inferencia_fin",      # termina MiniFASNetV2
    "antispoof_fin",                 # decisión real/spoof publicada
    "reconocimiento_inicio",         # Modelo 3 tomó Buffer 2
    "reconocimiento_alineado",       # termina alignCrop
    "reconocimiento_embedding",      # termina SFace
    "reconocimiento_fin",            # comparación con la galería publicada
    "gestor_resultado",              # el Pipeline Manager recibió el resultado
    "gestor_senal",                  # LED verde/rojo solicitado al GPIO
    "pulso_apertura",                # la salida de apertura pasó a HIGH
)

# Duraciones que se calculan para cada intento: (columna, desde, hasta).
INTERVALOS = (
    ("preparacion_deteccion_ms", "captura", "deteccion_inicio"),
    ("yunet_ms", "deteccion_inicio", "deteccion_fin"),
    ("recorte_y_buffers_ms", "deteccion_fin", "muestras_listas"),
    ("traspaso_a_antispoof_ms", "muestras_listas", "antispoof_inicio"),
    ("preparacion_antispoof_ms", "antispoof_inicio", "antispoof_inferencia_inicio"),
    ("minifasnet_ms", "antispoof_inferencia_inicio", "antispoof_inferencia_fin"),
    ("antispoof_total_ms", "antispoof_inicio", "antispoof_fin"),
    ("traspaso_a_reconocimiento_ms", "antispoof_fin", "reconocimiento_inicio"),
    ("alineado_ms", "reconocimiento_inicio", "reconocimiento_alineado"),
    ("sface_ms", "reconocimiento_alineado", "reconocimiento_embedding"),
    ("comparacion_galeria_ms", "reconocimiento_embedding", "reconocimiento_fin"),
    ("reconocimiento_total_ms", "reconocimiento_inicio", "reconocimiento_fin"),
    ("gestor_ms", "gestor_resultado", "gestor_senal"),
    ("senal_a_pulso_ms", "gestor_senal", "pulso_apertura"),
    # Totales vistos por el usuario
    ("total_hasta_decision_ms", "captura", "gestor_resultado"),
    ("total_hasta_senal_ms", "captura", "gestor_senal"),
    ("total_hasta_pulso_ms", "captura", "pulso_apertura"),
)

COLUMNAS_DATOS = (
    "fecha_hora",
    "resultado",
    "puntaje_deteccion",
    "puntaje_antispoof",
    "similitud",
    "personas_en_galeria",
)

COLUMNAS_DETECCION = (
    "fecha_hora",
    "yunet_ms",
    "rostro",
    "modo",
)


def ahora():
    """Reloj monótono de alta resolución, común a todos los hilos."""

    return time.perf_counter()


class MedidorTiempos:
    """Acumula las marcas del intento en curso y las guarda en CSV."""

    def __init__(self):
        self._lock = threading.Lock()
        self.habilitado = False
        self.registrar_cuadros = False
        self.ruta_intentos = None
        self.ruta_deteccion = None
        self._actual = None
        self._datos = {}
        self._cuadros = []

    # ------------------------------------------------------------ config
    def configurar(self, config):
        """Lee la sección `metricas` del YAML."""

        metricas = (config or {}).get("metricas", {}) or {}
        self.habilitado = bool(metricas.get("habilitadas", False))
        self.registrar_cuadros = bool(
            metricas.get("registrar_cada_cuadro", True)
        )

        carpeta = Path(metricas.get("carpeta", "data/metricas"))
        if not carpeta.is_absolute():
            carpeta = CARPETA_PROYECTO / carpeta

        self.ruta_intentos = carpeta / "tiempos_pipeline.csv"
        self.ruta_deteccion = carpeta / "tiempos_deteccion.csv"

        if self.habilitado:
            carpeta.mkdir(parents=True, exist_ok=True)
            print("Medición de tiempos activa:", carpeta)

    # ------------------------------------------------------------ intentos
    def nuevo_intento(self, marcas):
        """Comienza un intento con las marcas tomadas por la detección."""

        if not self.habilitado:
            return

        with self._lock:
            # Un intento anterior que nunca se cerró (por ejemplo, el pulso no
            # llegó a ejecutarse) se guarda igualmente para no perder datos.
            if self._actual is not None and "gestor_resultado" in self._actual:
                self._escribir_intento("incompleto")
            self._actual = dict(marcas)
            self._datos = {}

    def marcar(self, hito, instante=None):
        """Registra la primera vez que el intento alcanza un hito."""

        if not self.habilitado:
            return

        instante = ahora() if instante is None else instante
        with self._lock:
            if self._actual is not None:
                self._actual.setdefault(hito, instante)

    def anotar(self, **datos):
        """Agrega datos informativos (puntajes, tamaño de la galería)."""

        if not self.habilitado:
            return

        with self._lock:
            if self._actual is not None:
                self._datos.update(
                    {k: v for k, v in datos.items() if v is not None}
                )

    def cerrar(self, resultado, **datos):
        """Escribe el intento en curso y lo da por terminado."""

        if not self.habilitado:
            return

        with self._lock:
            if self._actual is None:
                return
            self._datos.update(
                {k: v for k, v in datos.items() if v is not None}
            )
            self._escribir_intento(resultado)

    def descartar(self):
        """Olvida el intento en curso (errores o limpieza del pipeline)."""

        with self._lock:
            self._actual = None
            self._datos = {}

    def hay_intento(self):
        with self._lock:
            return self._actual is not None

    # ------------------------------------------------------------ detector
    def registrar_deteccion(self, duracion_s, hubo_rostro, descanso):
        """Guarda la duración de una inferencia de YuNet."""

        if not (self.habilitado and self.registrar_cuadros):
            return

        fila = (
            datetime.now().isoformat(timespec="milliseconds"),
            f"{duracion_s * 1000:.2f}",
            int(bool(hubo_rostro)),
            "descanso" if descanso else "activo",
        )
        with self._lock:
            self._cuadros.append(fila)
            if len(self._cuadros) >= 100:
                self._volcar_cuadros()

    def cerrar_archivos(self):
        """Escribe lo pendiente; se llama al apagar SmartGate."""

        if not self.habilitado:
            return

        with self._lock:
            self._volcar_cuadros()

    # ------------------------------------------------------------ interno
    def _escribir_intento(self, resultado):
        marcas = self._actual
        datos = self._datos
        self._actual = None
        self._datos = {}

        fila = {
            "fecha_hora": datetime.now().isoformat(timespec="seconds"),
            "resultado": resultado,
        }
        for clave in COLUMNAS_DATOS[2:]:
            valor = datos.get(clave)
            fila[clave] = (
                f"{valor:.4f}" if isinstance(valor, float) else valor
            )

        for columna, desde, hasta in INTERVALOS:
            if desde in marcas and hasta in marcas:
                fila[columna] = f"{(marcas[hasta] - marcas[desde]) * 1000:.2f}"

        # El traspaso al gestor parte del último modelo que trabajó.
        ultimo_modelo = marcas.get(
            "reconocimiento_fin",
            marcas.get("antispoof_fin"),
        )
        if ultimo_modelo is not None and "gestor_resultado" in marcas:
            fila["traspaso_a_gestor_ms"] = (
                f"{(marcas['gestor_resultado'] - ultimo_modelo) * 1000:.2f}"
            )

        columnas = (
            list(COLUMNAS_DATOS)
            + [c for c, _d, _h in INTERVALOS[:12]]
            + ["traspaso_a_gestor_ms"]
            + [c for c, _d, _h in INTERVALOS[12:]]
        )
        _agregar_fila(self.ruta_intentos, columnas, fila)

    def _volcar_cuadros(self):
        if not self._cuadros:
            return
        filas, self._cuadros = self._cuadros, []
        nuevo = not self.ruta_deteccion.exists()
        with self.ruta_deteccion.open("a", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            if nuevo:
                escritor.writerow(COLUMNAS_DETECCION)
            escritor.writerows(filas)


def _agregar_fila(ruta, columnas, fila):
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        if nuevo:
            escritor.writeheader()
        escritor.writerow({c: fila.get(c, "") for c in columnas})


# Instancia compartida por todos los hilos.
medidor = MedidorTiempos()
