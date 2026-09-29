"""Señales compartidas utilizadas para coordinar los hilos de SmartGate."""

from dataclasses import dataclass
from threading import Event


@dataclass
class Synchronization:
    """Agrupa todas las señales compartidas por el sistema."""

    # Indica el estado físico del portón.
    # SET: portón cerrado.
    # CLEAR: portón abierto.
    gate_closed: Event

    # Indica si Modelo 1 puede buscar una persona.
    # Solamente el Pipeline Manager debe volver a colocarla en SET.
    detection_enabled: Event

    # Indica que Buffer 1 está listo para ser consumido por Modelo 2.
    buffer1_ready: Event

    # Indica que Buffer 2 puede ser consumido por Modelo 3.
    recognition_ready: Event

    # Indican si cada modelo está detenido en un punto seguro.
    # SET: modelo esperando.
    # CLEAR: modelo trabajando.
    model1_idle: Event
    model2_idle: Event
    model3_idle: Event

    # Solicita a todos los hilos que terminen.
    shutdown: Event


def create_synchronization(gate_is_closed: bool) -> Synchronization:
    """Crea todas las señales con un estado inicial conocido."""

    synchronization = Synchronization(
        gate_closed=Event(),
        detection_enabled=Event(),
        buffer1_ready=Event(),
        recognition_ready=Event(),
        model1_idle=Event(),
        model2_idle=Event(),
        model3_idle=Event(),
        shutdown=Event(),
    )

    # Al iniciar todavía no hay modelos trabajando.
    synchronization.model1_idle.set()
    synchronization.model2_idle.set()
    synchronization.model3_idle.set()

    # El estado inicial del portón deberá obtenerse posteriormente desde GPIO.
    if gate_is_closed:
        synchronization.gate_closed.set()

    # detection_enabled permanece en CLEAR.
    # El Pipeline Manager decidirá si puede habilitar la primera detección.

    return synchronization