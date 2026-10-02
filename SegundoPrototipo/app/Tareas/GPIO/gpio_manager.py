import threading
import queue
import time
import gpiod

from gpio_comandos import gpio_comando_queue
from core.sync import Synchronization
import comandos_worker
import fc_worker

#hilo de manejo de pines gpio

def gpio_manager(config):

    chip = config["chip"]

    pin_fc = config["pins"]["final_carrera"]

    pin_led_activo = config["pins"]["led_activo"]
    pin_led_procesando = config["pins"]["led_procesando"]
    pin_led_aceptado = config["pins"]["led_aceptado"]
    pin_led_rechazado = config["pins"]["led_rechazado"]

    pin_abrir = config["pins"]["abrir_porton"]

    pulse_tiempo = config["gate"]["pulse_tiempo"]


    # ========================================================
    # CONFIGURAR FINAL DE CARRERA
    # ========================================================


    # Se necesita solicitar una linea para llegar al pin fisico a traves del kernel
    # Esta linea es unica y no soporta que otra aplicacion la solicite al mismo tiempo
    fc_request = gpiod.request_lines(
        chip,
        consumer="smartgate-fc",
        config={
            pin_fc: gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT,
                edge_detection=gpiod.line.Edge.BOTH
            )
        }
    )


    # ========================================================
    # CONFIGURAR SALIDAS
    # ========================================================

    output_request = gpiod.request_lines(
        chip,
        consumer="smartgate-outputs",
        config={
            (
                pin_led_activo,
                pin_led_procesando,
                pin_led_aceptado,
                pin_led_rechazado,
                pin_abrir
            ): gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT
            )
        }
    )


    # ========================================================
    # ESTADO INICIAL DE SALIDAS
    # ========================================================

    output_request.set_values({
        pin_led_activo: gpiod.line.Value.INACTIVE,
        pin_led_procesando: gpiod.line.Value.INACTIVE,
        pin_led_aceptado: gpiod.line.Value.INACTIVE,
        pin_led_rechazado: gpiod.line.Value.INACTIVE,
        pin_abrir: gpiod.line.Value.INACTIVE
    })


    # ========================================================
    # LEER ESTADO INICIAL DEL FINAL DE CARRERA
    # ========================================================

    fc_value = fc_request.get_value(pin_fc)

    if fc_value == gpiod.line.Value.INACTIVE:
        # LOW -> portón cerrado
        gate_closed.set()

    else:
        # HIGH -> portón no cerrado
        gate_closed.clear()


    # ========================================================
    # CREAR HILOS INTERNOS
    # ========================================================

    fc_thread = threading.Thread(
        target=fc_worker,
        args=(fc_request,),
        name="GPIO-FC"
    )

    command_thread = threading.Thread(
        target=comandos_worker,
        args=(
            output_request,
            pin_led_activo,
            pin_led_procesando,
            pin_led_aceptado,
            pin_led_rechazado,
            pin_abrir,
            pulse_tiempo
        ),
        name="GPIO-Comandos"
    )


    # ========================================================
    # ARRANCAR HILOS INTERNOS
    # ========================================================

    fc_thread.start()
    command_thread.start()
