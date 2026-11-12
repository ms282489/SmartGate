"""Comprueba la vista comprimida y la captura web sin usar una cámara."""

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import cv2
import numpy as np


CARPETA_MODULO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA_MODULO))

from capturar_dataset_web import (  # noqa: E402
    PAGINA,
    EstadoWeb,
    codificar_preview,
    crear_handler,
)


class GuardadorFalso:
    def __init__(self):
        self.guardadas = []
        self.errores = []

    def agregar(self, nombre, imagen, metadatos=None):
        self.guardadas.append((nombre, imagen.copy(), dict(metadatos)))
        return True


DATOS_SESION = {
    "person_id": "p001",
    "person_alias": "Mateo",
    "session_id": "s01",
    "label_name": "spoof_screen",
    "medium_id": "phone01",
    "source_content": "photo",
    "lighting": "natural",
    "location": "porton",
    "notes": "prueba",
}


imagen = np.zeros((960, 1280, 3), dtype=np.uint8)
imagen[:, :] = (20, 80, 160)

jpeg = codificar_preview(imagen, ancho=640, calidad=60)
preview = cv2.imdecode(
    np.frombuffer(jpeg, dtype=np.uint8),
    cv2.IMREAD_COLOR,
)

assert preview.shape == (480, 640, 3)
assert len(jpeg) < imagen.nbytes

guardador = GuardadorFalso()
estado = EstadoWeb("real_mateo", guardador)
estado.publicar_imagen(imagen)

try:
    estado.capturar()
except RuntimeError as error:
    assert "datos de la sesion" in str(error)
else:
    raise AssertionError("Se permitio capturar sin configurar la sesion")

sesion = estado.configurar_sesion(DATOS_SESION)
resultado = estado.capturar()
assert resultado["fotos"] == 1
assert resultado["fotos_sesion"] == 1
assert resultado["image_id"].startswith("img_")
assert len(guardador.guardadas) == 1
assert guardador.guardadas[0][0] == "real_mateo"
assert guardador.guardadas[0][1].shape == (960, 1280, 3)
assert guardador.guardadas[0][2]["image_id"] == resultado["image_id"]
assert guardador.guardadas[0][2]["person_id"] == "p001"
assert guardador.guardadas[0][2]["width"] == 1280
assert guardador.guardadas[0][2]["height"] == 960

estado.publicar_preview(jpeg, 19.8)
version, jpeg_publicado, detenido = estado.esperar_preview(-1, timeout=0)
assert version == 1
assert jpeg_publicado == jpeg
assert detenido is False
estado_actual = estado.estado()
assert estado_actual["fotos"] == 1
assert estado_actual["fotos_sesion"] == 1
assert estado_actual["fps"] == 19.8
assert estado_actual["error"] is None
assert estado_actual["sesion"] == sesion

estado.detener()
_version, _jpeg, detenido = estado.esperar_preview(version, timeout=0)
assert detenido is True

# Comprobar los endpoints usados por el navegador sobre un puerto temporal.
estado_http = EstadoWeb("real_mateo", GuardadorFalso())
estado_http.publicar_imagen(imagen)
estado_http.publicar_preview(jpeg, 19.8)
servidor = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    crear_handler(estado_http, "<html>SmartGate</html>"),
)
hilo_servidor = threading.Thread(target=servidor.serve_forever)
hilo_servidor.start()
url_base = f"http://127.0.0.1:{servidor.server_port}"

with urlopen(f"{url_base}/", timeout=2) as respuesta:
    assert respuesta.status == 200
    assert b"SmartGate" in respuesta.read()

contenido = json.dumps(DATOS_SESION).encode("utf-8")
with urlopen(
    Request(
        f"{url_base}/api/session",
        data=contenido,
        headers={"Content-Type": "application/json"},
        method="POST",
    ),
    timeout=2,
) as respuesta:
    sesion_http = json.loads(respuesta.read())["sesion"]
    assert sesion_http["person_id"] == "p001"
    assert sesion_http["capture_group_id"].startswith("cap_")

with urlopen(
    Request(f"{url_base}/api/capture", method="POST"),
    timeout=2,
) as respuesta:
    captura_http = json.loads(respuesta.read())
    assert captura_http["fotos"] == 1
    assert captura_http["fotos_sesion"] == 1
    assert captura_http["image_id"].startswith("img_")

with urlopen(f"{url_base}/api/status", timeout=2) as respuesta:
    assert json.loads(respuesta.read())["fotos"] == 1

with urlopen(f"{url_base}/frame.jpg?v=1", timeout=2) as respuesta:
    assert respuesta.status == 200
    assert respuesta.headers.get_content_type() == "image/jpeg"
    assert respuesta.read() == jpeg

assert 'id="vista-camara"' in PAGINA
assert "/frame.jpg?v=" in PAGINA

with urlopen(
    Request(f"{url_base}/api/stop", method="POST"),
    timeout=2,
) as respuesta:
    assert json.loads(respuesta.read()) == {"detenido": True}

hilo_servidor.join(timeout=2)
assert not hilo_servidor.is_alive()
servidor.server_close()

print("Vista, formulario, IDs, servidor web y captura: correctos")
