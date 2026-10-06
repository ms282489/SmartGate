"""Control del flujo principal del pipeline."""

from queue import Queue

from core.sync import Synchronization
from core.states import MensajePipeline, PipelineState


def inicializar_pipeline(
    sincronizacion: Synchronization,
) -> PipelineState:
    """Establece el estado inicial y decide si puede comenzar la detección."""

    # Comenzamos desde una condición segura.
    sincronizacion.detection_enabled.clear()

    porton_esta_cerrado = sincronizacion.gate_closed.is_set()

    if porton_esta_cerrado:
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

    return PipelineState.WAIT_GATE_CLOSE


def ejecutar_pipeline(
    sincronizacion: Synchronization,
    cola_mensajes: Queue[MensajePipeline],
) -> PipelineState:
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

        if (
            mensaje is MensajePipeline.CANDIDATO_DETECTADO
            and estado_pipeline is PipelineState.IDLE
        ):
            sincronizacion.detection_enabled.clear()
            estado_pipeline = PipelineState.PROCESSING

    return estado_pipeline
