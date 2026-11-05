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

ruta_galeria = raiz / "data/galeria_rostros.npz"
ruta_embeddings = raiz / "data/embeddings.npy"
cantidad_rostros = 0

if ruta_galeria.exists():
    with np.load(ruta_galeria, allow_pickle=False) as galeria:
        embeddings = galeria["embeddings"]
        ids = galeria["ids"]
        nombres = galeria["nombres"]
    assert embeddings.ndim == 2
    assert embeddings.shape[1:] == (128,)
    assert len(ids) == len(nombres) == len(embeddings)
    assert np.isfinite(embeddings).all()
    cantidad_rostros = len(embeddings)
elif ruta_embeddings.exists():
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
assert config["camera"]["preview"]["enabled"] is True
assert config["camera"]["preview"]["width"] > 0
assert config["camera"]["preview"]["height"] > 0
if "supabase" in config:
    assert config["supabase"]["retry_seconds"] > 0
    assert config["supabase"]["gallery_refresh_seconds"] > 0

requirements = (
    raiz / "requirements.txt"
).read_text(encoding="utf-8").splitlines()

assert "pyserial" in requirements
assert "supabase>=2.24,<3" in requirements

servicio_systemd = raiz / "systemd/smartgate.service"
assert servicio_systemd.exists()
contenido_servicio = servicio_systemd.read_text(encoding="utf-8")
assert "WantedBy=graphical-session.target" in contenido_servicio
assert "app/main.py" in contenido_servicio
assert "network-online.target" not in contenido_servicio

print("Rostros en respaldo local:", cantidad_rostros)
print("Archivos y configuración: correctos")
