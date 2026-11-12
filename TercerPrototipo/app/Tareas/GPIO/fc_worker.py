from core.states import MensajePipeline


def actualizar_estado_final_carrera(
    valor_actual,
    valor_cerrado,
    sincronizacion,
    cola_mensajes,
):
    """Publica el estado físico indicado por el final de carrera."""

    if valor_actual == valor_cerrado:
        sincronizacion.gate_closed.set()
        cola_mensajes.put(MensajePipeline.PORTON_CERRADO)
        return

    # La ausencia de la señal de cerrado significa que el portón está
    # abierto, abriendo o cerrando. Cortar la detección inmediatamente.
    sincronizacion.gate_closed.clear()
    sincronizacion.detection_enabled.clear()
    cola_mensajes.put(MensajePipeline.PORTON_ABIERTO)


def fc_worker(
    fc_request,
    pin_fc,
    valor_cerrado,
    sincronizacion,
    cola_mensajes,
):
    while True:

        # El hilo queda bloqueado esperando un evento del GPIO
        fc_request.wait_edge_events()

        # Consumir los flancos pendientes y leer el nivel físico actual. Esto
        # evita deducir el estado solamente por el tipo del último flanco.
        eventos = fc_request.read_edge_events()
        if not eventos:
            continue

        actualizar_estado_final_carrera(
            fc_request.get_value(pin_fc),
            valor_cerrado,
            sincronizacion,
            cola_mensajes,
        )
