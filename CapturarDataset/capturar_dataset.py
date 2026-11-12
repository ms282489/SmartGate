"""Captura independiente de fotografías para el dataset SmartGate."""

import argparse
import csv
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml
from camara import crear_camara


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
SALIDA_PREDETERMINADA = RAIZ_PROYECTO / "dataset"

ETIQUETAS = {
    "spoof_print": 0,
    "real": 1,
    "spoof_screen": 2,
}

ILUMINACIONES = {
    "unknown",
    "natural",
    "artificial",
    "low",
    "backlight",
    "mixed",
}

CONTENIDOS_ORIGEN = {"none", "photo", "video"}

CAMPOS_METADATA = [
    "image_id",
    "image_path",
    "captured_at_utc",
    "person_id",
    "person_alias",
    "session_id",
    "capture_group_id",
    "label_id",
    "label_name",
    "attack_type",
    "medium_id",
    "source_content",
    "lighting",
    "location",
    "camera_id",
    "width",
    "height",
    "notes",
]


def validar_nombre(nombre):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", nombre):
        raise ValueError("El nombre solo admite letras ASCII, numeros, _ y -")
    return nombre


def validar_identificador(valor, campo):
    """Valida IDs destinados a carpetas y al manifiesto del dataset."""

    valor = str(valor or "").strip()
    if not valor:
        raise ValueError(f"{campo} es obligatorio")
    if len(valor) > 64:
        raise ValueError(f"{campo} no puede superar 64 caracteres")
    try:
        return validar_nombre(valor)
    except ValueError as error:
        raise ValueError(
            f"{campo} solo admite letras ASCII, numeros, _ y -"
        ) from error


def _texto_corto(valor, campo, maximo):
    valor = str(valor or "").strip()
    if len(valor) > maximo:
        raise ValueError(f"{campo} no puede superar {maximo} caracteres")
    return valor


def normalizar_metadatos_sesion(datos):
    """Valida los datos elegidos una vez al comenzar una captura."""

    if not isinstance(datos, dict):
        raise ValueError("Los datos de sesion deben ser un objeto JSON")

    person_id = validar_identificador(datos.get("person_id"), "person_id")
    label_name = str(datos.get("label_name") or "").strip()
    if label_name not in ETIQUETAS:
        raise ValueError("label_name debe ser real, spoof_print o spoof_screen")

    session_id = str(datos.get("session_id") or "").strip()
    if not session_id:
        session_id = datetime.now().strftime("s_%Y%m%d_%H%M%S")
    session_id = validar_identificador(session_id, "session_id")

    lighting = str(datos.get("lighting") or "unknown").strip()
    if lighting not in ILUMINACIONES:
        raise ValueError("Condicion de iluminacion no valida")

    source_content = str(datos.get("source_content") or "none").strip()
    if source_content not in CONTENIDOS_ORIGEN:
        raise ValueError("Contenido de origen no valido")

    medium_id = str(datos.get("medium_id") or "").strip()
    if label_name == "real":
        medium_id = "none"
        source_content = "none"
    else:
        medium_id = validar_identificador(medium_id, "medium_id")

    if label_name == "spoof_screen" and source_content == "none":
        raise ValueError(
            "Para una pantalla indica si se muestra una foto o un video"
        )

    return {
        "person_id": person_id,
        "person_alias": _texto_corto(
            datos.get("person_alias"),
            "person_alias",
            120,
        ),
        "session_id": session_id,
        "capture_group_id": "cap_" + uuid.uuid4().hex[:16],
        "label_id": ETIQUETAS[label_name],
        "label_name": label_name,
        "attack_type": (
            "none"
            if label_name == "real"
            else label_name.removeprefix("spoof_")
        ),
        "medium_id": medium_id,
        "source_content": source_content,
        "lighting": lighting,
        "location": _texto_corto(datos.get("location"), "location", 120),
        "notes": _texto_corto(datos.get("notes"), "notes", 500),
    }


def crear_metadatos_captura(sesion, camera_id, imagen):
    """Crea la identidad inmutable de una fotografía concreta."""

    if sesion is None:
        raise ValueError("Primero debes guardar los datos de la sesion")

    metadatos = dict(sesion)
    metadatos.update(
        {
            "image_id": "img_" + uuid.uuid4().hex,
            "captured_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "camera_id": validar_identificador(camera_id, "camera_id"),
            "width": int(imagen.shape[1]),
            "height": int(imagen.shape[0]),
        }
    )
    return metadatos


class Guardador:
    def __init__(self, raiz):
        self.raiz = Path(raiz)
        self.cola = queue.Queue(maxsize=32)
        self.errores = []
        self._metadata_inicializado = False
        self.hilo = threading.Thread(target=self._trabajar, daemon=False)
        self.hilo.start()

    def agregar(self, nombre, imagen, metadatos=None):
        try:
            self.cola.put_nowait(
                (
                    nombre,
                    imagen.copy(),
                    dict(metadatos) if metadatos is not None else None,
                )
            )
            return True
        except queue.Full:
            print("Cola de guardado llena; foto no capturada")
            return False

    def _reservar_destino_legacy(self, nombre):
        carpeta = self.raiz / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        numero = 1
        while True:
            destino = carpeta / f"{nombre}_{numero:04d}.jpg"
            try:
                descriptor = os.open(
                    destino,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                return destino, descriptor
            except FileExistsError:
                numero += 1

    def _reservar_destino_metadata(self, metadatos):
        for campo in (
            "image_id",
            "person_id",
            "session_id",
            "label_name",
        ):
            validar_identificador(metadatos.get(campo), campo)

        carpeta = (
            self.raiz
            / metadatos["label_name"]
            / metadatos["person_id"]
            / metadatos["session_id"]
        )
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{metadatos['image_id']}.jpg"
        descriptor = os.open(
            destino,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        return destino, descriptor

    def _agregar_metadata(self, destino, metadatos):
        ruta = self.raiz / "metadata.csv"
        fila = dict(metadatos)
        fila["image_path"] = destino.relative_to(self.raiz).as_posix()

        if not self._metadata_inicializado and ruta.exists() and ruta.stat().st_size:
            with ruta.open(newline="", encoding="utf-8") as archivo:
                encabezado = next(csv.reader(archivo), [])
            if encabezado != CAMPOS_METADATA:
                raise RuntimeError(
                    "metadata.csv tiene un encabezado incompatible; "
                    "no se agregaron datos"
                )
            self._metadata_inicializado = True

        escribir_encabezado = not ruta.exists() or ruta.stat().st_size == 0
        with ruta.open("a", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(
                archivo,
                fieldnames=CAMPOS_METADATA,
                extrasaction="ignore",
            )
            if escribir_encabezado:
                escritor.writeheader()
            escritor.writerow(
                {campo: fila.get(campo, "") for campo in CAMPOS_METADATA}
            )
            archivo.flush()
            os.fsync(archivo.fileno())
        self._metadata_inicializado = True

    def _trabajar(self):
        while True:
            item = self.cola.get()
            try:
                if item is None:
                    return
                nombre, imagen, metadatos = item
                if metadatos is None:
                    destino, fd = self._reservar_destino_legacy(nombre)
                else:
                    destino, fd = self._reservar_destino_metadata(metadatos)
                try:
                    ok, datos = cv2.imencode(
                        ".jpg",
                        imagen,
                        [cv2.IMWRITE_JPEG_QUALITY, 95],
                    )
                    if not ok:
                        raise RuntimeError("No se pudo codificar el JPEG")
                    with os.fdopen(fd, "wb") as archivo:
                        archivo.write(datos.tobytes())
                    if metadatos is not None:
                        self._agregar_metadata(destino, metadatos)
                    print(f"Guardada: {destino}")
                except Exception:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    destino.unlink(missing_ok=True)
                    raise
            except Exception as exc:
                self.errores.append(str(exc))
                print(f"ERROR al guardar: {exc}")
            finally:
                self.cola.task_done()

    def cerrar(self):
        self.cola.join()
        self.cola.put(None)
        self.hilo.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True, type=validar_nombre)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.yaml"),
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=SALIDA_PREDETERMINADA,
    )
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument(
        "--vista-fps",
        type=float,
        default=10.0,
        help=(
            "FPS maximos de la ventana. Un valor moderado evita "
            "saturar la conexion SSH."
        ),
    )
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps debe ser positivo")
    if args.vista_fps <= 0:
        parser.error("--vista-fps debe ser positivo")

    if (
        os.name != "nt"
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    ):
        parser.error(
            "no hay una pantalla disponible. Desde macOS inicia XQuartz "
            "y conectate a la Raspberry con: ssh -Y usuario@direccion"
        )

    with args.config.open(encoding="utf-8") as archivo:
        config = yaml.safe_load(archivo)["camera"].copy()
    config["fps"] = args.fps
    nombre = args.nombre
    camara = None
    guardador = None
    stop = threading.Event()
    lock = threading.Lock()
    ultimo = [None]
    version_imagen = [0]
    fallos = [0]

    def adquirir():
        while not stop.is_set():
            ok, imagen = camara.read()
            if ok:
                with lock:
                    ultimo[0] = imagen
                    version_imagen[0] += 1
                fallos[0] = 0
            else:
                fallos[0] += 1
                if fallos[0] >= 30:
                    stop.set()
                    break
                time.sleep(0.03)

    try:
        camara = crear_camara(config)
        if not camara.isOpened():
            raise RuntimeError("No se pudo abrir la camara")
        guardador = Guardador(args.salida)
        hilo = threading.Thread(target=adquirir, daemon=True)
        hilo.start()
        ventana = "SmartGate - dataset"
        try:
            cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(ventana, 960, 720)
        except cv2.error as error:
            raise RuntimeError(
                "No se pudo abrir la ventana. En macOS abre XQuartz y "
                "conectate con 'ssh -Y usuario@direccion'."
            ) from error

        print("ESPACIO=guardar | S=detener | N=nuevo nombre | Q/Esc=salir")
        print("Para reanudar una sesion detenida, presiona N y escribe el nombre.")
        print("Las fotografias se guardaran en:", args.salida.resolve())
        activo = True
        anterior = time.monotonic()
        cuadros = 0
        fps_vista = 0.0
        version_mostrada = -1
        proxima_vista = 0.0
        intervalo_vista = 1.0 / args.vista_fps
        capturas_solicitadas = 0
        aviso_captura_hasta = 0.0
        imagen = None

        while not stop.is_set():
            with lock:
                imagen = ultimo[0]
                version_actual = version_imagen[0]

            ahora = time.monotonic()
            if (
                imagen is not None
                and version_actual != version_mostrada
                and ahora >= proxima_vista
            ):
                visible = cv2.resize(imagen, (960, 720), interpolation=cv2.INTER_AREA)
                version_mostrada = version_actual
                proxima_vista = ahora + intervalo_vista
                cuadros += 1
                if ahora - anterior >= 1:
                    fps_vista = cuadros / (ahora - anterior)
                    anterior, cuadros = ahora, 0
                estado = (
                    f"{'ACTIVA' if activo else 'PAUSADA'} | {nombre} | "
                    f"fotos {capturas_solicitadas} | vista {fps_vista:.1f} FPS"
                )
                cv2.putText(
                    visible,
                    estado,
                    (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0) if activo else (0, 200, 255),
                    2,
                )
                cv2.putText(
                    visible,
                    "ESPACIO: FOTO | Q/ESC: SALIR",
                    (12, 705),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )

                if ahora < aviso_captura_hasta:
                    cv2.putText(
                        visible,
                        "FOTO CAPTURADA",
                        (350, 370),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 255, 0),
                        3,
                    )

                cv2.imshow(ventana, visible)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord('q'), ord('Q'), 27):
                break
            if tecla == ord(' '):
                if activo and imagen is not None:
                    if guardador.agregar(nombre, imagen):
                        capturas_solicitadas += 1
                        aviso_captura_hasta = time.monotonic() + 0.7
                        # Forzar un repintado para mostrar la confirmacion.
                        version_mostrada = -1
                else:
                    print("Sesion pausada o sin imagen disponible")
            elif tecla in (ord('s'), ord('S')):
                activo = False
                print("Sesion detenida; vista sigue activa")
            elif tecla in (ord('n'), ord('N')):
                activo = False
                print("Escribi el nuevo nombre en la terminal y presiona Enter")
                try:
                    nuevo = validar_nombre(input("Nuevo nombre: ").strip())
                    nombre, activo = nuevo, True
                    print(f"Sesion activa: {nombre}")
                except (ValueError, EOFError) as exc:
                    print(f"No se inicio otra sesion: {exc}")
            try:
                if cv2.getWindowProperty(ventana, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        stop.set()
        if camara is not None:
            if 'hilo' in locals():
                hilo.join(timeout=3)
            camara.release()
        if guardador is not None:
            print("Esperando a guardar las fotos pendientes...")
            guardador.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
