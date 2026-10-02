from core.sync import Synchronization
from core.states import PipelineState


def inicializar_pipeline(
    sincronizacion: Synchronization,
) -> PipelineState:
    """Establece el estado inicial y decide si puede comenzar la detección."""

    # Comenzamos desde una condición segura.
    sincronizacion.detection_enabled.clear()

    porton_esta_cerrado = (
        sincronizacion.gate_closed.is_set()
    )

    if porton_esta_cerrado:
        sincronizacion.detection_enabled.set()
        return PipelineState.IDLE

    return PipelineState.WAIT_GATE_CLOSE