"""Comprueba que la galería sobrevive sin conexión a Supabase."""

import tempfile
from pathlib import Path

import numpy as np

from Tareas.reconocimiento.galeria import (
    GaleriaCompartida,
    cargar_respaldo_local,
    guardar_respaldo_local,
)


with tempfile.TemporaryDirectory() as carpeta:
    ruta = Path(carpeta) / "galeria_rostros.npz"
    ruta_legacy = Path(carpeta) / "no_existe.npy"
    personas = [
        {
            "id": "persona-1",
            "name": "Persona de prueba",
            "embedding": np.linspace(
                0.0,
                1.0,
                128,
                dtype=np.float32,
            ).reshape(1, -1),
        }
    ]

    guardar_respaldo_local(personas, ruta=ruta)
    cargadas = cargar_respaldo_local(
        ruta=ruta,
        ruta_legacy=ruta_legacy,
    )

    assert len(cargadas) == 1
    assert cargadas[0]["id"] == "persona-1"
    assert cargadas[0]["name"] == "Persona de prueba"
    assert np.array_equal(
        cargadas[0]["embedding"],
        personas[0]["embedding"],
    )

    galeria = GaleriaCompartida()
    galeria.reemplazar(cargadas)
    assert galeria.cantidad() == 1
    assert galeria.obtener()[0]["name"] == "Persona de prueba"

    guardar_respaldo_local([], ruta=ruta)
    assert cargar_respaldo_local(
        ruta=ruta,
        ruta_legacy=ruta_legacy,
    ) == []

print("Respaldo facial y modo offline: correctos")
