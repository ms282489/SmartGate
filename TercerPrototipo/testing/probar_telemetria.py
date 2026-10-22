"""Prueba la telemetría sin utilizar un puerto físico."""

import json
import time
from threading import Thread
from unittest.mock import MagicMock, patch

from core.sync import create_synchronization
from Tareas.telemetria.telemetria_worker import (
    registrar_evento,
    telemetria_worker,
)


config = {
    "telemetry": {
        "port": "PUERTO_SIMULADO",
        "baudrate": 115200,
        "interval": 1,
    }
}

sincronizacion = create_synchronization()
puerto_simulado = MagicMock()


with patch(
    "Tareas.telemetria.telemetria_worker.serial.Serial",
    return_value=puerto_simulado,
):
    telemetria_thread = Thread(
        target=telemetria_worker,
        args=(
            config,
            sincronizacion,
        ),
    )

    telemetria_thread.start()

    registrar_evento("APROBADO")
    registrar_evento("RECHAZADO")
    registrar_evento("RECHAZADO")
    registrar_evento("SPOOF")

    time.sleep(1.5)

    sincronizacion.shutdown.set()
    telemetria_thread.join()


assert puerto_simulado.write.call_count >= 1

datos_enviados = (
    puerto_simulado.write
    .call_args_list[0]
    .args[0]
    .decode("utf-8")
)

resumen = json.loads(datos_enviados)

assert resumen["aprobados"] == 1
assert resumen["rechazados"] == 2
assert resumen["spoof"] == 1

puerto_simulado.close.assert_called_once()

print("Resumen enviado:", resumen)
print("Prueba de telemetría: correcta")
