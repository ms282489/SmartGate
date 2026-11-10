"""Comprueba nombres y guardado JPEG sin acceder a una cámara."""

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

print("Nombres, ruta del dataset y guardado JPEG: correctos")
