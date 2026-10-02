import queue
import time
import gpiod

from gpio_comandos import gpio_comando_queue


def command_worker(
    output_request,
    pin_led_activo,
    pin_led_procesando,
    pin_led_aceptado,
    pin_led_rechazado,
    pin_abrir,
    pulse_tiempo
):

    pulso_activo = False
    fin_pulso = 0.0

    while True:

        # Si hay un pulso activo, esperar como máximo hasta que termine
        if pulso_activo:

            tiempo_restante = fin_pulso - time.monotonic()

            if tiempo_restante <= 0:

                output_request.set_value(
                    pin_abrir,
                    gpiod.line.Value.INACTIVE
                )

                pulso_activo = False
                continue

            timeout = tiempo_restante

        # Si no hay un pulso activo, esperar indefinidamente por un comando nuevo
        else:
            timeout = None


        # Esperar comando
        try:
            comando = gpio_comando_queue.get(timeout=timeout)

        except queue.Empty:
            # Venció el tiempo del pulso
            continue


        # LED ACTIVO
        if comando == "ACTIVO":

            output_request.set_values({
                pin_led_activo: gpiod.line.Value.ACTIVE,
                pin_led_procesando: gpiod.line.Value.INACTIVE,
                pin_led_aceptado: gpiod.line.Value.INACTIVE,
                pin_led_rechazado: gpiod.line.Value.INACTIVE
            })


        # LED PROCESANDO
        elif comando == "PROCESANDO":

            output_request.set_values({
                pin_led_activo: gpiod.line.Value.INACTIVE,
                pin_led_procesando: gpiod.line.Value.ACTIVE,
                pin_led_aceptado: gpiod.line.Value.INACTIVE,
                pin_led_rechazado: gpiod.line.Value.INACTIVE
            })


        # LED ACEPTADO
        elif comando == "ACEPTADO":

            output_request.set_values({
                pin_led_activo: gpiod.line.Value.INACTIVE,
                pin_led_procesando: gpiod.line.Value.INACTIVE,
                pin_led_aceptado: gpiod.line.Value.ACTIVE,
                pin_led_rechazado: gpiod.line.Value.INACTIVE
            })


        # LED RECHAZADO
        elif comando == "RECHAZADO":

            output_request.set_values({
                pin_led_activo: gpiod.line.Value.INACTIVE,
                pin_led_procesando: gpiod.line.Value.INACTIVE,
                pin_led_aceptado: gpiod.line.Value.INACTIVE,
                pin_led_rechazado: gpiod.line.Value.ACTIVE
            })


        # PULSO DE APERTURA
        elif comando == "ABRIR":

            if not pulso_activo:

                output_request.set_value(
                    pin_abrir,
                    gpiod.line.Value.ACTIVE
                )

                pulso_activo = True
                fin_pulso = time.monotonic() + pulse_tiempo