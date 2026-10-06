import time

import gpiod

from Tareas.GPIO.gpio_comandos import gpio_comando_queue


def command_worker(
    output_request,
    pin_led_activo,
    pin_led_procesando,
    pin_led_aceptado,
    pin_led_rechazado,
    pin_abrir,
    pulse_tiempo,
):

    while True:

        # Esperar hasta recibir un comando
        comando = gpio_comando_queue.get()

        # LED ACTIVO
        if comando == "ACTIVO":

            output_request.set_values(
                {
                    pin_led_activo: gpiod.line.Value.ACTIVE,
                    pin_led_procesando: gpiod.line.Value.INACTIVE,
                    pin_led_aceptado: gpiod.line.Value.INACTIVE,
                    pin_led_rechazado: gpiod.line.Value.INACTIVE,
                }
            )

        # LED PROCESANDO
        elif comando == "PROCESANDO":

            output_request.set_values(
                {
                    pin_led_activo: gpiod.line.Value.INACTIVE,
                    pin_led_procesando: gpiod.line.Value.ACTIVE,
                    pin_led_aceptado: gpiod.line.Value.INACTIVE,
                    pin_led_rechazado: gpiod.line.Value.INACTIVE,
                }
            )

        # LED ACEPTADO
        elif comando == "ACEPTADO":

            output_request.set_values(
                {
                    pin_led_activo: gpiod.line.Value.INACTIVE,
                    pin_led_procesando: gpiod.line.Value.INACTIVE,
                    pin_led_aceptado: gpiod.line.Value.ACTIVE,
                    pin_led_rechazado: gpiod.line.Value.INACTIVE,
                }
            )

        # LED RECHAZADO
        elif comando == "RECHAZADO":

            output_request.set_values(
                {
                    pin_led_activo: gpiod.line.Value.INACTIVE,
                    pin_led_procesando: gpiod.line.Value.INACTIVE,
                    pin_led_aceptado: gpiod.line.Value.INACTIVE,
                    pin_led_rechazado: gpiod.line.Value.ACTIVE,
                }
            )

        # PULSO DE APERTURA
        elif comando == "ABRIR":

            # Activar la salida que ordena abrir el portón
            output_request.set_value(
                pin_abrir,
                gpiod.line.Value.ACTIVE,
            )

            # Mantener la salida activa durante el tiempo configurado
            time.sleep(pulse_tiempo/1000)

            # Desactivar nuevamente la salida
            output_request.set_value(
                pin_abrir,
                gpiod.line.Value.INACTIVE,
            )