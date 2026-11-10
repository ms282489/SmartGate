"""Captura el dataset desde un navegador conectado por un tunel SSH."""

import argparse
import html
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import yaml

from camara import crear_camara
from capturar_dataset import (
    SALIDA_PREDETERMINADA,
    Guardador,
    validar_nombre,
)


PAGINA = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SmartGate Dataset</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #101214; color: #f3f5f7; }
    main { width: min(100%, 960px); margin: auto; padding: 16px; }
    header { display: flex; gap: 12px; justify-content: space-between;
             align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
    h1 { font-size: 1.2rem; margin: 0; }
    #estado { color: #8ee6a8; font-variant-numeric: tabular-nums; }
    .video { position: relative; background: #050607; border-radius: 12px;
             overflow: hidden; border: 1px solid #343a40; }
    img { display: block; width: 100%; aspect-ratio: 4 / 3;
          object-fit: contain; }
    #aviso { position: absolute; inset: 0; display: grid; place-items: center;
             font-size: clamp(1.5rem, 5vw, 3rem); font-weight: 800;
             color: #53f27e; opacity: 0; transition: opacity .12s; }
    #aviso.visible { opacity: 1; }
    nav { display: flex; gap: 10px; margin-top: 12px; }
    button { flex: 1; min-height: 48px; border: 0; border-radius: 10px;
             font-size: 1rem; font-weight: 700; cursor: pointer; }
    #capturar { background: #32c95b; color: #08140b; }
    #detener { background: #3b4147; color: white; }
    p { color: #adb5bd; margin: 10px 0 0; text-align: center; }
  </style>
</head>
<body>
<main>
  <header>
    <h1>SmartGate · __NOMBRE__</h1>
    <div id="estado">Conectando…</div>
  </header>
  <div class="video">
    <img src="/stream.mjpg" alt="Vista de la cámara">
    <div id="aviso">FOTO CAPTURADA</div>
  </div>
  <nav>
    <button id="capturar">Tomar foto · Espacio</button>
    <button id="detener">Finalizar</button>
  </nav>
  <p>La vista está comprimida; las fotos se guardan a resolución completa.</p>
</main>
<script>
  const estado = document.querySelector('#estado');
  const aviso = document.querySelector('#aviso');
  let capturando = false;

  async function actualizarEstado() {
    try {
      const respuesta = await fetch('/api/status', {cache: 'no-store'});
      const datos = await respuesta.json();
      estado.textContent = `Fotos ${datos.fotos} · ${datos.fps.toFixed(1)} FPS`;
      if (datos.error) estado.textContent += ` · ERROR: ${datos.error}`;
    } catch (_) {
      estado.textContent = 'Servidor desconectado';
    }
  }

  async function capturar() {
    if (capturando) return;
    capturando = true;
    try {
      const respuesta = await fetch('/api/capture', {method: 'POST'});
      const datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudo capturar');
      aviso.classList.add('visible');
      setTimeout(() => aviso.classList.remove('visible'), 500);
      actualizarEstado();
    } catch (error) {
      estado.textContent = `ERROR: ${error.message}`;
    } finally {
      capturando = false;
    }
  }

  document.querySelector('#capturar').addEventListener('click', capturar);
  document.querySelector('#detener').addEventListener('click', async () => {
    await fetch('/api/stop', {method: 'POST'});
    estado.textContent = 'Captura finalizada';
  });
  document.addEventListener('keydown', event => {
    if (event.code === 'Space' && !event.repeat) {
      event.preventDefault();
      capturar();
    }
  });
  setInterval(actualizarEstado, 500);
  actualizarEstado();
</script>
</body>
</html>
"""


class EstadoWeb:
    """Comparte el último cuadro con el codificador y el servidor HTTP."""

    def __init__(self, nombre, guardador):
        self.nombre = nombre
        self.guardador = guardador
        self._lock = threading.Lock()
        self._condicion = threading.Condition(self._lock)
        self._imagen = None
        self._jpeg = None
        self._version = 0
        self._fotos = 0
        self._fps = 0.0
        self._error = None
        self._detenido = False

    def publicar_imagen(self, imagen):
        with self._lock:
            self._imagen = imagen

    def obtener_imagen(self):
        with self._lock:
            return self._imagen

    def publicar_preview(self, jpeg, fps):
        with self._condicion:
            self._jpeg = jpeg
            self._fps = float(fps)
            self._version += 1
            self._condicion.notify_all()

    def esperar_preview(self, version, timeout=2.0):
        with self._condicion:
            self._condicion.wait_for(
                lambda: self._version != version or self._detenido,
                timeout=timeout,
            )
            return self._version, self._jpeg, self._detenido

    def capturar(self):
        with self._lock:
            imagen = self._imagen

        if imagen is None:
            raise RuntimeError("Todavia no hay una imagen disponible")

        if not self.guardador.agregar(self.nombre, imagen):
            raise RuntimeError("La cola de guardado esta llena")

        with self._lock:
            self._fotos += 1
            return self._fotos

    def informar_error(self, error):
        with self._lock:
            self._error = str(error)

    def estado(self):
        with self._lock:
            return {
                "fotos": self._fotos,
                "fps": self._fps,
                "error": self._error,
            }

    def detener(self):
        with self._condicion:
            self._detenido = True
            self._condicion.notify_all()


def codificar_preview(imagen, ancho, calidad):
    """Genera un JPEG pequeño sin modificar la fotografía original."""

    ancho = min(int(ancho), imagen.shape[1])
    escala = ancho / imagen.shape[1]
    alto = max(1, round(imagen.shape[0] * escala))

    if ancho == imagen.shape[1]:
        visible = imagen
    else:
        visible = cv2.resize(
            imagen,
            (ancho, alto),
            interpolation=cv2.INTER_AREA,
        )

    correcto, datos = cv2.imencode(
        ".jpg",
        visible,
        [cv2.IMWRITE_JPEG_QUALITY, int(calidad)],
    )
    if not correcto:
        raise RuntimeError("No se pudo codificar la vista JPEG")
    return datos.tobytes()


def crear_handler(estado, pagina):
    """Crea el controlador HTTP vinculado a una sesión concreta."""

    class Handler(BaseHTTPRequestHandler):
        def enviar_json(self, datos, estado_http=200):
            cuerpo = json.dumps(datos).encode("utf-8")
            self.send_response(estado_http)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path == "/":
                cuerpo = pagina.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(cuerpo)
                return

            if self.path == "/api/status":
                self.enviar_json(estado.estado())
                return

            if self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=frame",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                version = -1
                try:
                    while True:
                        nueva_version, jpeg, detenido = (
                            estado.esperar_preview(version)
                        )
                        if detenido:
                            break
                        if jpeg is None or nueva_version == version:
                            continue
                        version = nueva_version
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                        )
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            self.send_error(404)

        def do_POST(self):
            if self.path == "/api/capture":
                try:
                    fotos = estado.capturar()
                except RuntimeError as error:
                    self.enviar_json({"error": str(error)}, 409)
                else:
                    self.enviar_json({"fotos": fotos})
                return

            if self.path == "/api/stop":
                self.enviar_json({"detenido": True})
                threading.Thread(
                    target=self.server.shutdown,
                    daemon=True,
                ).start()
                return

            self.send_error(404)

        def log_message(self, formato, *argumentos):
            return

    return Handler


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
    parser.add_argument("--puerto", type=int, default=8765)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--vista-fps", type=float, default=20.0)
    parser.add_argument("--vista-ancho", type=int, default=640)
    parser.add_argument("--calidad-jpeg", type=int, default=60)
    args = parser.parse_args()

    if not 1 <= args.puerto <= 65535:
        parser.error("--puerto debe estar entre 1 y 65535")
    if args.fps <= 0 or args.vista_fps <= 0:
        parser.error("--fps y --vista-fps deben ser positivos")
    if args.vista_ancho <= 0:
        parser.error("--vista-ancho debe ser positivo")
    if not 1 <= args.calidad_jpeg <= 100:
        parser.error("--calidad-jpeg debe estar entre 1 y 100")

    with args.config.open(encoding="utf-8") as archivo:
        config = yaml.safe_load(archivo)["camera"].copy()
    config["fps"] = args.fps

    camara = crear_camara(config)
    if not camara.isOpened():
        raise RuntimeError("No se pudo abrir la camara")

    guardador = Guardador(args.salida)
    estado = EstadoWeb(args.nombre, guardador)
    detener = threading.Event()
    pagina = PAGINA.replace("__NOMBRE__", html.escape(args.nombre))
    servidor = ThreadingHTTPServer(
        ("127.0.0.1", args.puerto),
        crear_handler(estado, pagina),
    )

    def adquirir():
        fallos = 0
        while not detener.is_set():
            correcto, imagen = camara.read()
            if correcto:
                estado.publicar_imagen(imagen)
                fallos = 0
                continue

            fallos += 1
            if fallos >= 30:
                estado.informar_error("La camara dejo de entregar imagenes")
                detener.set()
                return
            detener.wait(0.03)

    def generar_preview():
        intervalo = 1.0 / args.vista_fps
        proxima = time.monotonic()
        inicio_medicion = proxima
        cuadros = 0
        fps_real = 0.0

        while not detener.is_set():
            ahora = time.monotonic()
            if ahora < proxima:
                detener.wait(proxima - ahora)
                continue

            imagen = estado.obtener_imagen()
            if imagen is None:
                detener.wait(0.01)
                continue

            try:
                jpeg = codificar_preview(
                    imagen,
                    args.vista_ancho,
                    args.calidad_jpeg,
                )
            except Exception as error:
                estado.informar_error(error)
                detener.set()
                return

            cuadros += 1
            ahora = time.monotonic()
            if ahora - inicio_medicion >= 1.0:
                fps_real = cuadros / (ahora - inicio_medicion)
                cuadros = 0
                inicio_medicion = ahora
            estado.publicar_preview(jpeg, fps_real)

            proxima += intervalo
            if proxima <= ahora:
                proxima = ahora + intervalo

    hilo_camara = threading.Thread(target=adquirir, daemon=True)
    hilo_preview = threading.Thread(target=generar_preview, daemon=True)
    hilo_camara.start()
    hilo_preview.start()

    print("Capturador web iniciado.")
    print(f"En el Mac abri: http://localhost:{args.puerto}")
    print("ESPACIO=guardar foto | boton Finalizar=cerrar")
    print("Las fotografias se guardaran en:", args.salida.resolve())

    try:
        servidor.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        detener.set()
        estado.detener()
        servidor.server_close()
        hilo_camara.join(timeout=3)
        hilo_preview.join(timeout=3)
        camara.release()
        print("Esperando a guardar las fotos pendientes...")
        guardador.cerrar()


if __name__ == "__main__":
    main()
