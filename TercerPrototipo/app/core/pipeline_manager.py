"""Control del flujo principal del pipeline."""

from queue import Queue
from core.buffers import limpiar_buffers
from core.states import (
    MensajePipeline,
    PipelineState,
    ResultadoPipeline,
)
from core.sync import Synchronization
from Tareas.GPIO.gpio_comandos import (
    signal_abrir_porton,
    signal_aceptado,
    signal_activo,
    signal_apagar,
    signal_procesando,
    signal_rechazado,
)
from Tareas.telemetria.telemetria_worker import (
    registrar_evento,
)
from Tareas.supabase.supabase_worker import (
    registrar_evento_supabase,
)


COLOR_ACTIVO = (0, 255, 0)
COLOR_PROCESANDO = (0, 165, 255)
COLOR_ACEPTADO = (0, 255, 0)
COLOR_RECHAZADO = (0, 0, 255)
COLOR_ESPERA = (0, 255, 255)


def actualizar_vista(vista_camara, texto, color):
    """Publica el estado del pipeline si la vista está habilitada."""

    if vista_camara is not None:
        vista_camara.actualizar_estado(texto, color)


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
    sincronizacion.detection_score = None
    sincronizacion.antispoof_score = None


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
    cola_mensajes: Queue[
        MensajePipeline | ResultadoPipeline
    ],
    config=None,
    vista_camara=None,
) -> PipelineState:
    """Ejecuta el control principal del pipeline."""

    gate_config = (config or {}).get("gate", {})
    modo_solo_camara = bool(
        gate_config.get("modo_solo_camara", False)
    )
    resultado_visible = max(
        0.0,
        float(gate_config.get("resultado_visible_segundos", 2.0)),
    )
    estado_pipeline = inicializar_pipeline(sincronizacion)

    if estado_pipeline is PipelineState.IDLE:
        actualizar_vista(
            vista_camara,
            "BUSCANDO ROSTRO",
            COLOR_ACTIVO,
        )
    else:
        actualizar_vista(
            vista_camara,
            "ESPERANDO CIERRE DEL PORTON",
            COLOR_ESPERA,
        )

    while True:
        try:
            elemento = cola_mensajes.get()

        except KeyboardInterrupt:
            elemento = MensajePipeline.APAGAR

        # Algunos workers envían solamente un mensaje.
        # Reconocimiento y antispoofing también pueden enviar
        # información como persona_id o puntuaciones.
        if isinstance(elemento, ResultadoPipeline):
            mensaje = elemento.mensaje
            resultado = elemento

        else:
            mensaje = elemento
            resultado = None

        if mensaje is MensajePipeline.APAGAR:
            actualizar_vista(
                vista_camara,
                "APAGANDO SMARTGATE",
                COLOR_ESPERA,
            )
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
            actualizar_vista(
                vista_camara,
                "PROCESANDO ROSTRO",
                COLOR_PROCESANDO,
            )

        elif (
            (
                mensaje is MensajePipeline.SPOOF_DETECTADO
                or mensaje is MensajePipeline.IDENTIDAD_RECHAZADA
            )
            and estado_pipeline is PipelineState.PROCESSING
        ):
            if mensaje is MensajePipeline.SPOOF_DETECTADO:
                registrar_evento("SPOOF")

                registrar_evento_supabase(
                    resultado="spoof",
                    antispoof=(
                        resultado.antispoof
                        if resultado is not None
                        else None
                    ),
                    deteccion=(
                        resultado.deteccion
                        if resultado is not None
                        else None
                    ),
                )
                texto_resultado = "SPOOF DETECTADO"

            else:
                registrar_evento("RECHAZADO")

                registrar_evento_supabase(
                    resultado="denied",
                    similitud=(
                        resultado.similitud
                        if resultado is not None
                        else None
                    ),
                    antispoof=(
                        resultado.antispoof
                        if resultado is not None
                        else None
                    ),
                    deteccion=(
                        resultado.deteccion
                        if resultado is not None
                        else None
                    ),
                )

                if resultado is not None and resultado.similitud is not None:
                    texto_resultado = (
                        "ACCESO RECHAZADO "
                        f"{resultado.similitud * 100:.1f}%"
                    )
                else:
                    texto_resultado = "ACCESO RECHAZADO"

            signal_rechazado()
            actualizar_vista(
                vista_camara,
                texto_resultado,
                COLOR_RECHAZADO,
            )

            if modo_solo_camara:
                sincronizacion.shutdown.wait(resultado_visible)

            estado_pipeline = habilitar_deteccion(
                sincronizacion
            )

            if modo_solo_camara:
                signal_activo()
                actualizar_vista(
                    vista_camara,
                    "BUSCANDO ROSTRO",
                    COLOR_ACTIVO,
                )

        elif (
            mensaje is MensajePipeline.IDENTIDAD_AUTORIZADA
            and estado_pipeline is PipelineState.PROCESSING
        ):
            sincronizacion.detection_enabled.clear()

            registrar_evento("APROBADO")

            registrar_evento_supabase(
                resultado="authorized",
                persona_id=(
                    resultado.persona_id
                    if resultado is not None
                    else None
                ),
                similitud=(
                    resultado.similitud
                    if resultado is not None
                    else None
                ),
                antispoof=(
                    resultado.antispoof
                    if resultado is not None
                    else None
                ),
                deteccion=(
                    resultado.deteccion
                    if resultado is not None
                    else None
                ),
            )

            signal_aceptado()

            if resultado is not None and resultado.similitud is not None:
                texto_resultado = (
                    "ACCESO AUTORIZADO "
                    f"{resultado.similitud * 100:.1f}%"
                )
            else:
                texto_resultado = "ACCESO AUTORIZADO"

            actualizar_vista(
                vista_camara,
                texto_resultado,
                COLOR_ACEPTADO,
            )

            if modo_solo_camara:
                sincronizacion.shutdown.wait(resultado_visible)
                estado_pipeline = habilitar_deteccion(
                    sincronizacion
                )
                signal_activo()
                actualizar_vista(
                    vista_camara,
                    "BUSCANDO ROSTRO",
                    COLOR_ACTIVO,
                )
            else:
                signal_abrir_porton()
                estado_pipeline = PipelineState.WAIT_GATE_OPEN

        elif mensaje is MensajePipeline.PORTON_ABIERTO:
            actualizar_vista(
                vista_camara,
                "PORTON ABIERTO",
                COLOR_ESPERA,
            )
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
            actualizar_vista(
                vista_camara,
                "BUSCANDO ROSTRO",
                COLOR_ACTIVO,
            )

        elif mensaje is MensajePipeline.ERROR:
            estado_pipeline = PipelineState.CLEANING
            limpiar_pipeline(sincronizacion)
            estado_pipeline = habilitar_deteccion(
                sincronizacion
            )

            signal_rechazado()
            actualizar_vista(
                vista_camara,
                "ERROR: REINTENTANDO",
                COLOR_RECHAZADO,
            )

    return estado_pipeline
