"""Comprueba Picamera2 y la OV5647 sin iniciar todo SmartGate."""

from pathlib import Path

import yaml

from core.camara import crear_camara


raiz = Path(__file__).resolve().parents[1]

with open(
    raiz / "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)

camara = crear_camara(config["camera"])

try:
    imagen = None

    # Descartar algunos cuadros adicionales luego del calentamiento.
    for _ in range(5):
        lectura_correcta, imagen = camara.read()

        if not lectura_correcta:
            raise RuntimeError(
                "Picamera2 no pudo capturar una imagen"
            )

    alto, ancho = imagen.shape[:2]

    assert ancho == config["camera"]["width"]
    assert alto == config["camera"]["height"]
    assert imagen.shape[2] == 3

    print(
        "Arducam OV5647 lista:",
        f"{ancho}x{alto},",
        "3 canales BGR",
    )

finally:
    camara.release()
