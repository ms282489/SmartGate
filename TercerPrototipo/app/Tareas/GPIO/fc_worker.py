import gpiod

from core.states import MensajePipeline


def fc_worker(
    fc_request,
    sincronizacion,
    cola_mensajes,
):
    while True:

        # El hilo queda bloqueado esperando un evento del GPIO
        fc_request.wait_edge_events()

        # Leer los eventos pendientes
        eventos = fc_request.read_edge_events()

        for evento in eventos:

            # LOW -> HIGH
            # El portón dejó la posición de cerrado
            if (
                evento.event_type
                == gpiod.EdgeEvent.Type.RISING_EDGE
            ):
                sincronizacion.gate_closed.clear()

                # Avisar al Pipeline Manager
                cola_mensajes.put(
                    MensajePipeline.PORTON_ABIERTO
                )

            # HIGH -> LOW
            # El portón llegó a cerrado
            elif (
                evento.event_type
                == gpiod.EdgeEvent.Type.FALLING_EDGE
            ):
                sincronizacion.gate_closed.set()

                # Avisar al Pipeline Manager
                cola_mensajes.put(
                    MensajePipeline.PORTON_CERRADO
                )