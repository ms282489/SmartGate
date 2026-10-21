"""Estados posibles del gestor del pipeline."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


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

class MensajePipeline(Enum):
    """Mensajes que los hilos pueden enviar al pipeline principal."""

    # Modelo 1 encontró una cara válida.
    CANDIDATO_DETECTADO = auto()

    # Modelo 2 determinó que la muestra no pertenece a una cara real.
    SPOOF_DETECTADO = auto()

    # Modelo 3 no reconoció a la persona.
    IDENTIDAD_RECHAZADA = auto()

    # Modelo 3 reconoció a una persona autorizada.
    IDENTIDAD_AUTORIZADA = auto()

    # El final de carrera indicó que el portón comenzó a abrirse.
    PORTON_ABIERTO = auto()

    # El final de carrera indicó que el portón terminó de cerrar.
    PORTON_CERRADO = auto()

    # Algún hilo encontró un error.
    ERROR = auto()

    # Se solicitó finalizar SmartGate.
    APAGAR = auto()


@dataclass(frozen=True)
class ResultadoPipeline:
    """Mensaje de un modelo junto con sus datos de decisión."""

    mensaje: MensajePipeline
    persona_id: Optional[str] = None
    similitud: Optional[float] = None
    antispoof: Optional[float] = None
    deteccion: Optional[float] = None
