"""Estados posibles del gestor del pipeline."""

from enum import Enum, auto


class PipelineState(Enum):
    """Situación general en la que puede encontrarse SmartGate."""

    # El pipeline está vacío y puede buscar una persona.
    IDLE = auto()

    # Una persona está siendo procesada por alguno de los modelos.
    PROCESSING = auto()

    # La persona fue autorizada y se espera que el portón comience a abrir.
    WAIT_GATE_OPEN = auto()

    # El portón está abierto y se espera que vuelva a cerrarse.
    WAIT_GATE_CLOSE = auto()

    # Se produjo una situación inesperada y deben normalizarse los recursos.
    CLEANING = auto()