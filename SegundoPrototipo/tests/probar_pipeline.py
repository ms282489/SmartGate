"""Pruebas simples del flujo principal sin utilizar hardware."""

from queue import Queue

from core.pipeline_manager import ejecutar_pipeline
from core.states import MensajePipeline, PipelineState
from core.sync import create_synchronization
from Tareas.GPIO.gpio_comandos import gpio_comando_queue


def vaciar_comandos_gpio():
    """Devuelve los comandos GPIO pendientes y deja la cola vacía."""

    comandos = []

    while not gpio_comando_queue.empty():
        comandos.append(gpio_comando_queue.get_nowait())

    return comandos


def ejecutar_secuencia(mensajes):
    """Ejecuta una secuencia de mensajes con el portón cerrado."""

    sincronizacion = create_synchronization()
    sincronizacion.gate_closed.set()

    cola_mensajes = Queue()

    for mensaje in mensajes:
        cola_mensajes.put(mensaje)

    estado = ejecutar_pipeline(
        sincronizacion,
        cola_mensajes,
    )

    comandos = vaciar_comandos_gpio()

    return estado, comandos


estado, comandos = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        MensajePipeline.IDENTIDAD_RECHAZADA,
        MensajePipeline.APAGAR,
    ]
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "PROCESANDO",
    "RECHAZADO",
    "APAGAR",
]

print("Prueba de rechazo: correcta")


estado, comandos = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        MensajePipeline.IDENTIDAD_AUTORIZADA,
        MensajePipeline.PORTON_ABIERTO,
        MensajePipeline.PORTON_CERRADO,
        MensajePipeline.APAGAR,
    ]
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "PROCESANDO",
    "ACEPTADO",
    "ABRIR",
    "ACTIVO",
    "APAGAR",
]

print("Prueba de autorización: correcta")


estado, comandos = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        MensajePipeline.ERROR,
        MensajePipeline.APAGAR,
    ]
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "PROCESANDO",
    "RECHAZADO",
    "APAGAR",
]

print("Prueba de recuperación de error: correcta")
print("Todas las pruebas del pipeline finalizaron correctamente")
