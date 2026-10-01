
#Importo funciones de core
from core.states import PipelineState
from core.sync import Synchronization

class GestorPipeline:
    """Mantiene el estado general del procesamiento."""

    @classmethod
    def crear(clase_gestor, sincronizacion: Synchronization):
        """Crea un gestor según el estado físico inicial del portón."""

        gestor = clase_gestor()
        gestor._sincronizacion = sincronizacion
        porton_esta_cerrado = sincronizacion.gate_closed.is_set()

        if porton_esta_cerrado:
            gestor._estado = PipelineState.IDLE
        else:
            gestor._estado = PipelineState.WAIT_GATE_CLOSE

        return gestor

    def consultar_estado(coordinador) -> PipelineState:
        """Devuelve el estado actual del pipeline."""

        return coordinador._estado


    def iniciar(coordinador) -> None:
        """Inicia el pipeline si el portón está cerrado."""

        # Antes de decidir, dejamos la detección bloqueada.
        coordinador._sincronizacion.detection_enabled.clear()

        porton_esta_cerrado = (coordinador._sincronizacion.gate_closed.is_set())

        if porton_esta_cerrado:
            # El sistema puede comenzar a buscar una persona.
            coordinador._estado = PipelineState.IDLE
            coordinador._sincronizacion.detection_enabled.set()
        else:
            # No se puede detectar hasta que el portón cierre.
            coordinador._estado = PipelineState.WAIT_GATE_CLOSE