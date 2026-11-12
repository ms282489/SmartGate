"""Comprueba nombres y guardado JPEG sin acceder a una cámara."""

import csv
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np


CARPETA_MODULO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARPETA_MODULO))

from capturar_dataset import (  # noqa: E402
    RAIZ_PROYECTO,
    SALIDA_PREDETERMINADA,
    Guardador,
    crear_metadatos_captura,
    normalizar_metadatos_sesion,
    validar_nombre,
)


assert SALIDA_PREDETERMINADA == RAIZ_PROYECTO / "dataset"
assert validar_nombre("real_mateo-01") == "real_mateo-01"

for nombre_invalido in ("", "mateo silva", "../otra-carpeta", "real/01"):
    try:
        validar_nombre(nombre_invalido)
    except ValueError:
        pass
    else:
        raise AssertionError(
            f"El nombre invalido fue aceptado: {nombre_invalido!r}"
        )

with tempfile.TemporaryDirectory() as temporal:
    salida = Path(temporal)
    imagen = np.zeros((48, 64, 3), dtype=np.uint8)
    imagen[:, :] = (20, 80, 160)

    guardador = Guardador(salida)
    assert guardador.agregar("real_mateo", imagen)
    assert guardador.agregar("real_mateo", imagen)
    guardador.cerrar()

    primera = salida / "real_mateo" / "real_mateo_0001.jpg"
    segunda = salida / "real_mateo" / "real_mateo_0002.jpg"
    assert primera.exists()
    assert segunda.exists()
    assert cv2.imread(str(primera)).shape == imagen.shape

    # Una sesión posterior debe continuar la numeración, no sobrescribir.
    guardador = Guardador(salida)
    assert guardador.agregar("real_mateo", imagen)
    guardador.cerrar()
    assert (salida / "real_mateo" / "real_mateo_0003.jpg").exists()

    sesion = normalizar_metadatos_sesion(
        {
            "person_id": "p001",
            "person_alias": "Mateo",
            "session_id": "s01",
            "label_name": "spoof_screen",
            "medium_id": "phone01",
            "source_content": "video",
            "lighting": "artificial",
            "location": "laboratorio",
            "notes": "brillo alto",
        }
    )
    metadatos = crear_metadatos_captura(
        sesion,
        "arducam_ov5647",
        imagen,
    )
    guardador = Guardador(salida)
    assert guardador.agregar("ignorado", imagen, metadatos)
    guardador.cerrar()

    foto = (
        salida
        / "spoof_screen"
        / "p001"
        / "s01"
        / f"{metadatos['image_id']}.jpg"
    )
    assert foto.exists()
    with (salida / "metadata.csv").open(newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    assert len(filas) == 1
    assert filas[0]["image_id"] == metadatos["image_id"]
    assert filas[0]["image_path"] == foto.relative_to(salida).as_posix()
    assert filas[0]["person_id"] == "p001"
    assert filas[0]["person_alias"] == "Mateo"
    assert filas[0]["label_id"] == "2"
    assert filas[0]["capture_group_id"] == sesion["capture_group_id"]
    assert filas[0]["width"] == "64"
    assert filas[0]["height"] == "48"

print("Nombres, JPEG, IDs y metadata.csv: correctos")
