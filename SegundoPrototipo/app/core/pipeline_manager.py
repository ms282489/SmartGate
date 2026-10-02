"""Control del flujo principal del pipeline."""

from core.sync import Synchronization
from core.states import MensajePipeline, PipelineState


def inicializar_pipeline(
    sincronizacion: Synchronization,
) -> PipelineState:
    """Decide el estado inicial según la posición del portón."""

    # La detección comienza bloqueada por seguridad.
    sincronizacion.detection_enabled.clear()

    porton_esta_cerrado = (
        sincronizacion.gate_closed.is_set()
    )

    if porton_esta_cerrado:
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

    return PipelineState.WAIT_GATE_CLOSE


def ejecutar_pipeline(
    sincronizacion,
    cola_mensajes,
):
    """Procesa en el hilo principal los mensajes de los workers."""

    estado_pipeline = inicializar_pipeline(
        sincronizacion
    )

    while True:
        # Permanece bloqueado hasta recibir un mensaje.
        mensaje = cola_mensajes.get()

        if mensaje is MensajePipeline.APAGAR:
            sincronizacion.detection_enabled.clear()
            sincronizacion.shutdown.set()
            break

        if mensaje is MensajePipeline.CANDIDATO_DETECTADO:
            sincronizacion.detection_enabled.clear()
            estado_pipeline = PipelineState.PROCESSING

    return estado_pipeline