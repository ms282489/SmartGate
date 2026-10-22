import threading
import time

from core.states import MensajePipeline
from Tareas.GPIO.gpio_comandos import gpio_comando_queue

try:
    import gpiod
except ModuleNotFoundError:
    # gpiod solo existe en Linux/Raspberry Pi. En una computadora
    # de desarrollo se utiliza el simulador definido más abajo.
    gpiod = None


def _command_worker_simulado(
    sincronizacion,
    cola_mensajes,
    pulse_tiempo,
):
    """Simula LEDs, relé y final de carrera fuera de la Raspberry."""

    while True:
        comando = gpio_comando_queue.get()

        if comando == "APAGAR":
            print("[GPIO simulado] Salidas apagadas")
            break

        print(f"[GPIO simulado] {comando}")

        if comando == "ABRIR":
            # Reproducir el ciclo que en la Raspberry generan el relé
            # y el final de carrera: abrir y volver a cerrar el portón.
            sincronizacion.gate_closed.clear()
            cola_mensajes.put(MensajePipeline.PORTON_ABIERTO)
            time.sleep(max(pulse_tiempo / 1000, 0.1))
            sincronizacion.gate_closed.set()
            cola_mensajes.put(MensajePipeline.PORTON_CERRADO)


# Hilo de manejo de pines GPIO
def gpio_manager(
    config,
    sincronizacion,
    cola_mensajes,
):

    chip = config["chip"]

    pin_fc = config["pins"]["final_carrera"]

    pin_led_activo = config["pins"]["led_activo"]
    pin_led_procesando = config["pins"]["led_procesando"]
    pin_led_aceptado = config["pins"]["led_aceptado"]
    pin_led_rechazado = config["pins"]["led_rechazado"]

    pin_abrir = config["pins"]["abrir_porton"]

    pulse_tiempo = config["gate"]["pulse_tiempo"]

    if gpiod is None:
        print(
            "gpiod no está disponible; "
            "GPIO ejecutándose en modo simulado"
        )
        sincronizacion.gate_closed.set()

        command_thread = threading.Thread(
            target=_command_worker_simulado,
            args=(
                sincronizacion,
                cola_mensajes,
                pulse_tiempo,
            ),
            name="GPIO-Simulado",
        )
        command_thread.start()
        return

    # Importar estos workers solamente cuando existe gpiod evita que
    # macOS intente cargar una biblioteca exclusiva de la Raspberry.
    from Tareas.GPIO.comandos_worker import command_worker
    from Tareas.GPIO.fc_worker import fc_worker

    # ========================================================
    # CONFIGURAR FINAL DE CARRERA
    # ========================================================

    # Se necesita solicitar una línea para llegar al pin físico
    # a través del kernel.
    # Esta línea es única y no soporta que otra aplicación
    # la solicite al mismo tiempo.
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
                pin_abrir,
            ): gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT
            )
        },
    )

    # ========================================================
    # ESTADO INICIAL DE SALIDAS
    # ========================================================

    output_request.set_values(
        {
            pin_led_activo: gpiod.line.Value.INACTIVE,
            pin_led_procesando: gpiod.line.Value.INACTIVE,
            pin_led_aceptado: gpiod.line.Value.INACTIVE,
            pin_led_rechazado: gpiod.line.Value.INACTIVE,
            pin_abrir: gpiod.line.Value.INACTIVE,
        }
    )

    # ========================================================
    # LEER ESTADO INICIAL DEL FINAL DE CARRERA
    # ========================================================

    fc_value = fc_request.get_value(pin_fc)

    if fc_value == gpiod.line.Value.INACTIVE:
        # LOW -> portón cerrado
        sincronizacion.gate_closed.set()

    else:
        # HIGH -> portón no cerrado
        sincronizacion.gate_closed.clear()

    # ========================================================
    # CREAR HILOS INTERNOS
    # ========================================================

    fc_thread = threading.Thread(
        target=fc_worker,
        args=(
            fc_request,
            sincronizacion,
            cola_mensajes,
        ),
        name="GPIO-FC",
        daemon=True,
    )

    command_thread = threading.Thread(
        target=command_worker,
        args=(
            output_request,
            pin_led_activo,
            pin_led_procesando,
            pin_led_aceptado,
            pin_led_rechazado,
            pin_abrir,
            pulse_tiempo,
        ),
        name="GPIO-Comandos",
    )

    # ========================================================
    # ARRANCAR HILOS INTERNOS
    # ========================================================

    fc_thread.start()
    command_thread.start()
