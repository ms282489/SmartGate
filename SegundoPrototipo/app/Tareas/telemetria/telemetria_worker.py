"""Envía un resumen periódico por el puerto serial."""

import json
import time
from datetime import datetime
from queue import Empty, Queue

import serial


telemetria_queue = Queue()


def registrar_evento(resultado):
    """Guarda un resultado para el próximo resumen."""

    telemetria_queue.put(resultado)


def telemetria_worker(
    config,
    sincronizacion,
):
    """Envía la telemetría automáticamente."""

    telemetry_config = config["telemetry"]

    puerto = telemetry_config["port"]
    baudios = telemetry_config["baudrate"]
    intervalo = telemetry_config["interval"]

    try:
        conexion = serial.Serial(
            port=puerto,
            baudrate=baudios,
            timeout=1,
        )

    except Exception as error:
        print("No se pudo abrir el puerto serial:", error)
        return

    aprobados = 0
    rechazados = 0
    intentos_spoof = 0

    ultimo_envio = time.monotonic()

    while not sincronizacion.shutdown.is_set():

        try:
            evento = telemetria_queue.get(timeout=1)

            if evento == "APROBADO":
                aprobados += 1

            elif evento == "RECHAZADO":
                rechazados += 1

            elif evento == "SPOOF":
                intentos_spoof += 1

        except Empty:
            pass

        tiempo_transcurrido = (
            time.monotonic() - ultimo_envio
        )

        if tiempo_transcurrido >= intervalo:

            resumen = {
                "fecha": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "aprobados": aprobados,
                "rechazados": rechazados,
                "spoof": intentos_spoof,
            }

            mensaje = json.dumps(resumen) + "\n"

            try:
                conexion.write(
                    mensaje.encode("utf-8")
                )

            except Exception as error:
                print(
                    "No se pudo enviar la telemetría:",
                    error,
                )
                break

            aprobados = 0
            rechazados = 0
            intentos_spoof = 0

            ultimo_envio = time.monotonic()

    conexion.close()