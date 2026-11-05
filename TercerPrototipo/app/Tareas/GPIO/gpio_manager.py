import threading

import gpiod

from Tareas.GPIO.comandos_worker import command_worker
from Tareas.GPIO.fc_worker import fc_worker


def gpio_manager(config, sincronizacion, cola_mensajes):
    """Inicializa GPIO; config es el YAML completo, no solo config["gpio"]."""

    gpio_config = config["gpio"]
    chip = gpio_config["chip"]

    pin_fc = gpio_config["pins"]["final_carrera"]
    pin_led_activo = gpio_config["pins"]["led_activo"]
    pin_led_aceptado = gpio_config["pins"]["led_aceptado"]
    pin_led_rechazado = gpio_config["pins"]["led_rechazado"]
    pin_abrir = gpio_config["pins"]["abrir_porton"]

    pulse_tiempo = config["gate"]["pulse_tiempo"]
    modo_solo_camara = bool(
        config["gate"].get("modo_solo_camara", False)
    )
    frecuencia_procesando = config["leds"]["frecuencia_procesando_hz"]

    if frecuencia_procesando <= 0:
        raise ValueError("leds.frecuencia_procesando_hz debe ser mayor que cero")

    fc_request = None

    if not modo_solo_camara:
        # FC: solicitud de entrada independiente de las salidas.
        fc_request = gpiod.request_lines(
            chip,
            consumer="smartgate-fc",
            config={
                pin_fc: gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    edge_detection=gpiod.line.Edge.BOTH,
                )
            },
        )

    # Las salidas se escriben solo desde el command_worker.
    output_request = gpiod.request_lines(
        chip,
        consumer="smartgate-outputs",
        config={
            (
                pin_led_activo,
                pin_led_aceptado,
                pin_led_rechazado,
                pin_abrir,
            ): gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            )
        },
    )

    # Estado inicial de indicadores: esperando usuario.
    output_request.set_values({
        pin_led_activo: gpiod.line.Value.ACTIVE,
        pin_led_aceptado: gpiod.line.Value.INACTIVE,
        pin_led_rechazado: gpiod.line.Value.INACTIVE,
        pin_abrir: gpiod.line.Value.INACTIVE,
    })

    fc_thread = None

    if modo_solo_camara:
        sincronizacion.gate_closed.set()
        print(
            "Modo solo cámara activo: "
            "se omite el final de carrera y la apertura del portón"
        )
    else:
        # Leer el FC al iniciar; no esperar al primer flanco.
        fc_value = fc_request.get_value(pin_fc)
        if fc_value == gpiod.line.Value.INACTIVE:
            sincronizacion.gate_closed.set()  # LOW: cerrado
        else:
            sincronizacion.gate_closed.clear()  # HIGH: no cerrado

        fc_thread = threading.Thread(
            target=fc_worker,
            args=(fc_request, sincronizacion, cola_mensajes),
            name="GPIO-FC",
            daemon=True,
        )

    command_thread = threading.Thread(
        target=command_worker,
        args=(
            output_request,
            pin_led_activo,
            pin_led_aceptado,
            pin_led_rechazado,
            pin_abrir,
            pulse_tiempo,
            frecuencia_procesando,
        ),
        name="GPIO-Comandos",
    )

    if fc_thread is not None:
        fc_thread.start()
    command_thread.start()
