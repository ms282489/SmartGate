"""Prueba el flujo principal sin utilizar hardware."""

from queue import Queue

from core.pipeline_manager import ejecutar_pipeline
from core.states import (
    MensajePipeline,
    PipelineState,
    ResultadoPipeline,
)
from core.sync import create_synchronization
from Tareas.GPIO.gpio_comandos import gpio_comando_queue
from Tareas.telemetria.telemetria_worker import telemetria_queue


def vaciar_cola(cola):
    """Devuelve los elementos pendientes y deja la cola vacía."""

    elementos = []

    while not cola.empty():
        elementos.append(cola.get_nowait())

    return elementos


def ejecutar_secuencia(
    mensajes,
    porton_cerrado=True,
    config=None,
    vista_camara=None,
):
    """Ejecuta una secuencia de mensajes del pipeline."""

    vaciar_cola(gpio_comando_queue)
    vaciar_cola(telemetria_queue)

    sincronizacion = create_synchronization()

    if porton_cerrado:
        sincronizacion.gate_closed.set()

    cola_mensajes = Queue()

    for mensaje in mensajes:
        cola_mensajes.put(mensaje)

    estado = ejecutar_pipeline(
        sincronizacion,
        cola_mensajes,
        config=config,
        vista_camara=vista_camara,
    )

    comandos = vaciar_cola(gpio_comando_queue)
    telemetria = vaciar_cola(telemetria_queue)

    return estado, comandos, telemetria


estado, comandos, telemetria = ejecutar_secuencia(
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
assert telemetria == ["RECHAZADO"]

print("Prueba de rechazo: correcta")


estado, comandos, telemetria = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        MensajePipeline.SPOOF_DETECTADO,
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
assert telemetria == ["SPOOF"]

print("Prueba de spoof: correcta")


estado, comandos, telemetria = ejecutar_secuencia(
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
assert telemetria == ["APROBADO"]

print("Prueba de autorización: correcta")


estado, comandos, telemetria = ejecutar_secuencia(
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
assert telemetria == []

print("Prueba de recuperación de error: correcta")


estado, comandos, telemetria = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        MensajePipeline.PORTON_ABIERTO,
        MensajePipeline.PORTON_CERRADO,
        MensajePipeline.APAGAR,
    ]
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "PROCESANDO",
    "ACTIVO",
    "APAGAR",
]
assert telemetria == []

print("Prueba de apertura inesperada: correcta")


estado, comandos, telemetria = ejecutar_secuencia(
    [
        MensajePipeline.PORTON_CERRADO,
        MensajePipeline.APAGAR,
    ],
    porton_cerrado=False,
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "APAGAR",
]
assert telemetria == []

print("Prueba de portón inicialmente abierto: correcta")


class VistaPrueba:
    def __init__(self):
        self.estados = []

    def actualizar_estado(self, texto, color):
        self.estados.append((texto, color))


vista = VistaPrueba()
estado, comandos, telemetria = ejecutar_secuencia(
    [
        MensajePipeline.CANDIDATO_DETECTADO,
        ResultadoPipeline(
            mensaje=MensajePipeline.IDENTIDAD_AUTORIZADA,
            persona_id="persona-1",
            similitud=0.91,
        ),
        MensajePipeline.APAGAR,
    ],
    config={
        "gate": {
            "modo_solo_camara": True,
            "resultado_visible_segundos": 0,
        }
    },
    vista_camara=vista,
)

assert estado is PipelineState.IDLE
assert comandos == [
    "ACTIVO",
    "PROCESANDO",
    "ACEPTADO",
    "ACTIVO",
    "APAGAR",
]
assert "ABRIR" not in comandos
assert telemetria == ["APROBADO"]
assert any(
    texto == "ACCESO AUTORIZADO 91.0%"
    for texto, _color in vista.estados
)

print("Prueba de modo solo cámara: correcta")
print("Todas las pruebas del pipeline finalizaron correctamente")
