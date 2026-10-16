"""Comprueba los archivos necesarios para ejecutar SmartGate."""

from pathlib import Path

import numpy as np
import yaml


raiz = Path(__file__).resolve().parents[1]

archivos_necesarios = [
    raiz / "app/Tareas/deteccion/face_detection_yunet_2023mar.onnx",
    raiz / "app/Tareas/antispoof/MiniFASNetV2.onnx",
    raiz / "app/Tareas/reconocimiento/face_recognition_sface_2021dec.onnx",
    raiz / "data/embeddings.npy",
    raiz / "config/config.yaml",
]

for archivo in archivos_necesarios:
    assert archivo.exists(), f"Falta el archivo: {archivo}"
    assert archivo.stat().st_size > 0, f"El archivo está vacío: {archivo}"

embeddings = np.load(
    raiz / "data/embeddings.npy"
)

assert embeddings.ndim == 2
assert len(embeddings) > 0
assert np.isfinite(embeddings).all()

with open(
    raiz / "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)

assert config["telemetry"]["port"] == "/dev/serial0"
assert config["telemetry"]["baudrate"] == 115200
assert config["telemetry"]["interval"] == 60

requirements = (
    raiz / "requirements.txt"
).read_text(encoding="utf-8").splitlines()

assert "pyserial" in requirements

print("Rostros registrados:", len(embeddings))
print("Archivos y configuración: correctos")
