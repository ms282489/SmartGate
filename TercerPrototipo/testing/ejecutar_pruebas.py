"""Ejecuta las pruebas que no requieren hardware real."""

import os
import subprocess
import sys
from pathlib import Path


raiz = Path(__file__).resolve().parents[1]
carpeta_pruebas = Path(__file__).resolve().parent

pruebas = [
    "probar_sintaxis.py",
    "probar_archivos.py",
    "probar_modo_offline.py",
    "probar_deteccion.py",
    "probar_pipeline.py",
    "probar_vista_camara.py",
    "probar_telemetria.py",
    "probar_metricas.py",
]

entorno = os.environ.copy()
entorno["PYTHONPATH"] = str(raiz / "app")

for nombre in pruebas:
    print("\nEjecutando:", nombre, flush=True)

    resultado = subprocess.run(
        [
            sys.executable,
            "-B",
            str(carpeta_pruebas / nombre),
        ],
        cwd=raiz,
        env=entorno,
    )

    if resultado.returncode != 0:
        print("\nLa prueba falló:", nombre)
        sys.exit(1)

print("\nTodas las pruebas sin hardware finalizaron correctamente")
