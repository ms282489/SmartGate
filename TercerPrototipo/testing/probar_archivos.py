"""Comprueba los archivos necesarios para ejecutar SmartGate."""

from pathlib import Path

import numpy as np
import yaml


raiz = Path(__file__).resolve().parents[1]

archivos_necesarios = [
    raiz / "app/Tareas/deteccion/face_detection_yunet_2023mar.onnx",
    raiz / "app/Tareas/antispoof/MiniFASNetV2.onnx",
    raiz / "app/Tareas/reconocimiento/face_recognition_sface_2021dec.onnx",
    raiz / "config/config.yaml",
]

for archivo in archivos_necesarios:
    assert archivo.exists(), f"Falta el archivo: {archivo}"
    assert archivo.stat().st_size > 0, f"El archivo está vacío: {archivo}"

ruta_embeddings = raiz / "data/embeddings.npy"
cantidad_rostros = 0

if ruta_embeddings.exists():
    embeddings = np.load(ruta_embeddings)
    assert embeddings.ndim == 2
    assert np.isfinite(embeddings).all()
    cantidad_rostros = len(embeddings)

with open(
    raiz / "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)

assert config["telemetry"]["port"] == "/dev/serial0"
assert config["telemetry"]["baudrate"] == 115200
assert config["telemetry"]["interval"] == 60
assert config["camera"]["backend"] == "picamera2"
assert config["camera"]["width"] == 1280
assert config["camera"]["height"] == 960

requirements = (
    raiz / "requirements.txt"
).read_text(encoding="utf-8").splitlines()

assert "pyserial" in requirements

print("Rostros en respaldo local:", cantidad_rostros)
print("Archivos y configuración: correctos")
