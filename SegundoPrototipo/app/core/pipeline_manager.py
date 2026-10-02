<<<<<<< HEAD
"""Control del flujo principal del pipeline."""

from core.sync import Synchronization
from core.states import MensajePipeline, PipelineState
from queue import Queue


def inicializar_pipeline(sincronizacion: Synchronization,) -> PipelineState:
=======
from core.sync import Synchronization
from core.states import PipelineState


def inicializar_pipeline(
    sincronizacion: Synchronization,
) -> PipelineState:
>>>>>>> d82404a3d651f52f523d41bc929a5aaf9d24dffa
    """Establece el estado inicial y decide si puede comenzar la detección."""

    # Comenzamos desde una condición segura.
    sincronizacion.detection_enabled.clear()

    porton_esta_cerrado = (
        sincronizacion.gate_closed.is_set()
    )

    if porton_esta_cerrado:
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

<<<<<<< HEAD
    return PipelineState.WAIT_GATE_CLOSE

def ejecutar_pipeline(sincronizacion, cola_mensajes):
    """Ejecuta el control principal del pipeline."""

    estado_pipeline = inicializar_pipeline(
        sincronizacion
    )

    while True:
        mensaje = cola_mensajes.get()

        if mensaje is MensajePipeline.APAGAR:
            sincronizacion.detection_enabled.clear()
            sincronizacion.shutdown.set()
            break

        if mensaje is MensajePipeline.CANDIDATO_DETECTADO:
            sincronizacion.detection_enabled.clear()
            estado_pipeline = PipelineState.PROCESSING

    return estado_pipeline
=======
    return PipelineState.WAIT_GATE_CLOSE
>>>>>>> d82404a3d651f52f523d41bc929a5aaf9d24dffa
