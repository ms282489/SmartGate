"""Control del flujo principal del pipeline."""

from queue import Queue

from core.sync import Synchronization
from core.states import MensajePipeline, PipelineState
from Tareas.GPIO.gpio_comandos import signal_abrir_porton


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

    estado_pipeline = inicializar_pipeline(sincronizacion)

    while True:
        mensaje = cola_mensajes.get()

        if mensaje is MensajePipeline.APAGAR:
            sincronizacion.detection_enabled.clear()
            sincronizacion.shutdown.set()
            break

        elif (
            mensaje is MensajePipeline.CANDIDATO_DETECTADO
            and estado_pipeline is PipelineState.IDLE
        ):
            sincronizacion.detection_enabled.clear()
            estado_pipeline = PipelineState.PROCESSING

        elif (
            (
                mensaje is MensajePipeline.SPOOF_DETECTADO
                or mensaje is MensajePipeline.IDENTIDAD_RECHAZADA
            )
            and estado_pipeline is PipelineState.PROCESSING
        ):
            estado_pipeline = habilitar_deteccion(sincronizacion)

        elif (
            mensaje is MensajePipeline.IDENTIDAD_AUTORIZADA
            and estado_pipeline is PipelineState.PROCESSING
        ):
            sincronizacion.detection_enabled.clear()
            signal_abrir_porton()
            estado_pipeline = PipelineState.WAIT_GATE_OPEN

        elif (
            mensaje is MensajePipeline.PORTON_ABIERTO
            and estado_pipeline is PipelineState.WAIT_GATE_OPEN
        ):
            sincronizacion.gate_closed.clear()
            sincronizacion.detection_enabled.clear()
            estado_pipeline = PipelineState.WAIT_GATE_CLOSE

        elif (
            mensaje is MensajePipeline.PORTON_CERRADO
            and estado_pipeline is PipelineState.WAIT_GATE_CLOSE
        ):
            sincronizacion.gate_closed.set()
            estado_pipeline = habilitar_deteccion(sincronizacion)

    return estado_pipeline

def habilitar_deteccion(
    sincronizacion: Synchronization,
) -> PipelineState:
    sincronizacion.detection_enabled.clear()

    if sincronizacion.gate_closed.is_set():
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

    return PipelineState.WAIT_GATE_CLOSE