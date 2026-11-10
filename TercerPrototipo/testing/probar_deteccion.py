"""Prueba la cadencia y el escalado del detector sin usar una cámara."""

import numpy as np

from Tareas.deteccion.deteccion_worker import (
    ControlCadenciaDeteccion,
    escalar_deteccion,
)


control = ControlCadenciaDeteccion(
    segundos_sin_rostro=5.0,
    intervalo_activo=0.05,
    intervalo_descanso=0.2,
)
control.reiniciar(0.0)

assert control.debe_procesar(0.0)
assert not control.debe_procesar(0.01)
control.registrar_sin_rostro(4.99)
assert not control.en_descanso
control.registrar_sin_rostro(5.0)
assert control.en_descanso
assert not control.debe_procesar(5.19)
assert control.debe_procesar(5.20)

control.registrar_rostro(5.20)
assert not control.en_descanso
assert control.debe_procesar(5.20)

rostro = np.array(
    [
        10,
        20,
        30,
        40,
        11,
        21,
        12,
        22,
        13,
        23,
        14,
        24,
        15,
        25,
        0.93,
    ],
    dtype=np.float32,
)
escalado = escalar_deteccion(rostro, 2.0, 2.0)

np.testing.assert_allclose(escalado[:14], rostro[:14] * 2.0)
assert escalado[-1] == rostro[-1]
np.testing.assert_array_equal(rostro[:4], [10, 20, 30, 40])

print("Cadencia y escalado de detección: correctos")
