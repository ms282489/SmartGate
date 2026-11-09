"""Captura independiente de fotografías para el dataset SmartGate."""
import argparse
import os
import queue
import re
import threading
import time
from pathlib import Path

import cv2
import yaml
from camara import crear_camara


def validar_nombre(nombre):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", nombre):
        raise ValueError("El nombre solo admite letras ASCII, numeros, _ y -")
    return nombre


class Guardador:
    def __init__(self, raiz):
        self.raiz = Path(raiz)
        self.cola = queue.Queue(maxsize=32)
        self.errores = []
        self.hilo = threading.Thread(target=self._trabajar, daemon=False)
        self.hilo.start()

    def agregar(self, nombre, imagen):
        try:
            self.cola.put_nowait((nombre, imagen.copy()))
            return True
        except queue.Full:
            print("Cola de guardado llena; foto no capturada")
            return False

    def _trabajar(self):
        while True:
            item = self.cola.get()
            try:
                if item is None:
                    return
                nombre, imagen = item
                carpeta = self.raiz / nombre
                carpeta.mkdir(parents=True, exist_ok=True)
                # Enumerar en el escritor evita colisiones entre capturas pendientes.
                numero = 1
                while True:
                    destino = carpeta / f"{nombre}_{numero:04d}.jpg"
                    try:
                        fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        break
                    except FileExistsError:
                        numero += 1
                try:
                    ok, datos = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    if not ok:
                        raise RuntimeError("No se pudo codificar el JPEG")
                    with os.fdopen(fd, "wb") as archivo:
                        archivo.write(datos.tobytes())
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
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--salida", type=Path, default=Path(__file__).with_name("dataset"))
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps debe ser positivo")
    with args.config.open(encoding="utf-8") as archivo:
        config = yaml.safe_load(archivo)["camera"].copy()
    config["fps"] = args.fps
    nombre = args.nombre
    camara = None
    guardador = None
    stop = threading.Event()
    lock = threading.Lock()
    ultimo = [None]
    fallos = [0]

    def adquirir():
        while not stop.is_set():
            ok, imagen = camara.read()
            if ok:
                with lock:
                    ultimo[0] = imagen
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
        cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(ventana, 960, 720)
        print("ESPACIO=guardar | S=detener | N=nuevo nombre | Q/Esc=salir")
        print("Para reanudar una sesion detenida, presiona N y escribe el nombre.")
        activo = True
        anterior = time.monotonic()
        cuadros = 0
        fps_vista = 0.0
        while not stop.is_set():
            with lock:
                imagen = ultimo[0]
            if imagen is not None:
                visible = cv2.resize(imagen, (960, 720), interpolation=cv2.INTER_AREA)
                cuadros += 1
                ahora = time.monotonic()
                if ahora - anterior >= 1:
                    fps_vista = cuadros / (ahora - anterior)
                    anterior, cuadros = ahora, 0
                estado = f"{'ACTIVA' if activo else 'PAUSADA'} | {nombre} | vista {fps_vista:.1f} FPS"
                cv2.putText(visible, estado, (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, (0, 255, 0) if activo else (0, 200, 255), 2)
                cv2.imshow(ventana, visible)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord('q'), ord('Q'), 27):
                break
            if tecla == ord(' '):
                if activo and imagen is not None:
                    guardador.agregar(nombre, imagen)
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
