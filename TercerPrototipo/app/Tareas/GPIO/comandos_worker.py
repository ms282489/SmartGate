import time
from queue import Empty

import gpiod

from core.metricas import medidor
from Tareas.GPIO.gpio_comandos import gpio_comando_queue


def command_worker(
    output_request,
    pin_led_activo,
    pin_led_aceptado,
    pin_led_rechazado,
    pin_abrir,
    pulse_tiempo,
    frecuencia_procesando,
):
    """Gestiona las salidas desde un solo hilo, sin accesos GPIO concurrentes."""

    if frecuencia_procesando <= 0:
        raise ValueError("frecuencia_procesando debe ser mayor que cero")

    # Un ciclo ON/OFF tiene dos toggles.
    semiperiodo = 1.0 / (2.0 * frecuencia_procesando)
    proximo_toggle = None
    led_encendido = False

    def escribir_leds(activo, aceptado=False, rechazado=False):
        output_request.set_values({
            pin_led_activo: (gpiod.line.Value.ACTIVE if activo else gpiod.line.Value.INACTIVE),
            pin_led_aceptado: (gpiod.line.Value.ACTIVE if aceptado else gpiod.line.Value.INACTIVE),
            pin_led_rechazado: (gpiod.line.Value.ACTIVE if rechazado else gpiod.line.Value.INACTIVE),
        })

    while True:
        # Sin parpadeo, bloquear indefinidamente hasta recibir un comando.
        # Con parpadeo, esperar hasta el siguiente instante programado.
        espera = None if proximo_toggle is None else max(
            0.0, proximo_toggle - time.monotonic()
        )

        try:
            comando = gpio_comando_queue.get(timeout=espera)
        except Empty:
            # Ha vencido el plazo: alternar el LED de estado.
            led_encendido = not led_encendido
            output_request.set_value(
                pin_led_activo,
                gpiod.line.Value.ACTIVE if led_encendido else gpiod.line.Value.INACTIVE,
            )

            # Referencia absoluta: evita acumular el tiempo de ejecución.
            proximo_toggle += semiperiodo
            ahora = time.monotonic()
            if proximo_toggle <= ahora:
                # Si Linux se atrasó, saltar instantes vencidos.
                pasos = int((ahora - proximo_toggle) / semiperiodo) + 1
                proximo_toggle += pasos * semiperiodo
            continue

        # Comandos visuales cancelan cualquier patrón previo.
        if comando == "ACTIVO":
            proximo_toggle = None
            led_encendido = True
            escribir_leds(activo=True)

        elif comando == "PROCESANDO":
            # Comenzar con el LED encendido y alternar a frecuencia fija.
            led_encendido = True
            escribir_leds(activo=True)
            proximo_toggle = time.monotonic() + semiperiodo

        elif comando == "ACEPTADO":
            proximo_toggle = None
            led_encendido = False
            escribir_leds(activo=False, aceptado=True)

        elif comando == "RECHAZADO":
            proximo_toggle = None
            led_encendido = False
            escribir_leds(activo=False, rechazado=True)

        elif comando == "ABRIR":
            # Mantener el comportamiento previo y no cambiar el patrón visual.
            try:
                output_request.set_value(pin_abrir, gpiod.line.Value.ACTIVE)
                # Instante en que la central recibe la orden de apertura.
                medidor.marcar("pulso_apertura")
                medidor.cerrar("autorizado")
                time.sleep(pulse_tiempo / 1000)
            finally:
                output_request.set_value(pin_abrir, gpiod.line.Value.INACTIVE)

        elif comando == "APAGAR":
            proximo_toggle = None
            output_request.set_values({
                pin_led_activo: gpiod.line.Value.INACTIVE,
                pin_led_aceptado: gpiod.line.Value.INACTIVE,
                pin_led_rechazado: gpiod.line.Value.INACTIVE,
                pin_abrir: gpiod.line.Value.INACTIVE,
            })
            break
