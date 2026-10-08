"""Control del flujo principal del pipeline."""

from queue import Queue

from core.buffers import limpiar_buffers
from core.states import MensajePipeline, PipelineState
from core.sync import Synchronization
from Tareas.GPIO.gpio_comandos import (
    signal_abrir_porton,
    signal_aceptado,
    signal_activo,
    signal_apagar,
    signal_procesando,
    signal_rechazado,
)


def habilitar_deteccion(
    sincronizacion: Synchronization,
) -> PipelineState:
    """Habilita la detección si el portón está cerrado."""

    sincronizacion.detection_enabled.clear()

    if sincronizacion.gate_closed.is_set():
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

    return PipelineState.WAIT_GATE_CLOSE


def limpiar_pipeline(
    sincronizacion: Synchronization,
):
    """Espera a los modelos y limpia los recursos compartidos."""

    # Impedir que Modelo 1 comience otra detección
    sincronizacion.detection_enabled.clear()

    # Esperar que los modelos lleguen a un punto seguro
    sincronizacion.model1_idle.wait()
    sincronizacion.model2_idle.wait()
    sincronizacion.model3_idle.wait()

    # Vaciar los buffers
    limpiar_buffers()

    # Limpiar las señales entre los modelos
    sincronizacion.buffer1_ready.clear()
    sincronizacion.recognition_ready.clear()


def inicializar_pipeline(
    sincronizacion: Synchronization,
) -> PipelineState:
    """Establece el estado inicial del pipeline."""

    estado = habilitar_deteccion(sincronizacion)

    if estado is PipelineState.IDLE:
        signal_activo()

    return estado


def ejecutar_pipeline(
    sincronizacion: Synchronization,
    cola_mensajes: Queue[MensajePipeline],
) -> PipelineState:
    """Ejecuta el control principal del pipeline."""

    estado_pipeline = inicializar_pipeline(sincronizacion)

    while True:
        try:
            mensaje = cola_mensajes.get()

        except KeyboardInterrupt:
            mensaje = MensajePipeline.APAGAR

        if mensaje is MensajePipeline.APAGAR:
            sincronizacion.shutdown.set()

            # Despertar los modelos para que puedan terminar
            sincronizacion.detection_enabled.set()
            sincronizacion.buffer1_ready.set()
            sincronizacion.recognition_ready.set()

            # Apagar las salidas GPIO
            signal_apagar()

            break

        elif (
            mensaje is MensajePipeline.CANDIDATO_DETECTADO
            and estado_pipeline is PipelineState.IDLE
        ):
            sincronizacion.detection_enabled.clear()
            signal_procesando()
            estado_pipeline = PipelineState.PROCESSING

        elif (
            (
                mensaje is MensajePipeline.SPOOF_DETECTADO
                or mensaje is MensajePipeline.IDENTIDAD_RECHAZADA
            )
            and estado_pipeline is PipelineState.PROCESSING
        ):
            estado_pipeline = habilitar_deteccion(
                sincronizacion
            )

            signal_rechazado()

        elif (
            mensaje is MensajePipeline.IDENTIDAD_AUTORIZADA
            and estado_pipeline is PipelineState.PROCESSING
        ):
            sincronizacion.detection_enabled.clear()

            signal_aceptado()
            signal_abrir_porton()
            estado_pipeline = PipelineState.WAIT_GATE_OPEN

        elif mensaje is MensajePipeline.PORTON_ABIERTO:
            sincronizacion.gate_closed.clear()
            sincronizacion.detection_enabled.clear()

            # Apertura esperada después de una autorización
            if estado_pipeline is PipelineState.WAIT_GATE_OPEN:
                estado_pipeline = PipelineState.WAIT_GATE_CLOSE

            # Apertura inesperada mientras el sistema trabajaba
            else:
                estado_pipeline = PipelineState.CLEANING
                limpiar_pipeline(sincronizacion)
                estado_pipeline = PipelineState.WAIT_GATE_CLOSE

        elif (
            mensaje is MensajePipeline.PORTON_CERRADO
            and estado_pipeline is PipelineState.WAIT_GATE_CLOSE
        ):
            sincronizacion.gate_closed.set()
            estado_pipeline = habilitar_deteccion(
                sincronizacion
            )

            signal_activo()

        elif mensaje is MensajePipeline.ERROR:
            estado_pipeline = PipelineState.CLEANING
            limpiar_pipeline(sincronizacion)
            estado_pipeline = habilitar_deteccion(
                sincronizacion
            )

            signal_rechazado()

    return estado_pipeline
