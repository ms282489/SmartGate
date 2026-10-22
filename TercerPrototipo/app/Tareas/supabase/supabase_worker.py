"""
Worker encargado de enviar los eventos de acceso a Supabase.

Este módulo trabaja en segundo plano para que una conexión lenta
o una caída de internet no detenga el reconocimiento facial ni
la apertura del portón.

Se tienen dos tipos de manejo de las variables, una es diccionario, para trabajar con la supabase y 
luego esta el Json que es para guardar localmente los datos
"""

import json
import time
from pathlib import Path
from threading import Lock

# Empty representa que una cola no recibió elementos durante
# el tiempo de espera. Queue es una cola segura para usar con hilos.
from queue import Empty, Queue
from dotenv import dotenv_values

# create_client crea la conexión con Supabase.
from supabase import create_client


# ------------------------------------------------------------------
# RUTAS
# ------------------------------------------------------------------

# __file__ contiene la ruta de este archivo:
#
# SegundoPrototipo/app/Tareas/supabase/supabase_worker.py
#
# parents[3] retrocede hasta la carpeta SegundoPrototipo.
CARPETA_PROYECTO = Path(__file__).resolve().parents[3]


# Archivo que contiene:
# - URL de Supabase
# - clave publicable
# - email del dispositivo
# - contraseña del dispositivo
RUTA_ENV = CARPETA_PROYECTO / "app" / ".env"


# Si no hay internet, los eventos se guardarán acá.
RUTA_EVENTOS_PENDIENTES = (
    CARPETA_PROYECTO
    / "data"
    / "eventos_pendientes.jsonl"
)


# ------------------------------------------------------------------
# COLA EN MEMORIA
# ------------------------------------------------------------------

# Esta cola comunica el pipeline con el worker de Supabase.
#
# El pipeline coloca eventos y continúa trabajando.
# El worker los extrae y los envía en segundo plano.
#
# Queue es segura para usar simultáneamente desde varios hilos.
eventos_supabase_queue = Queue()


# Evita llenar la base con detecciones repetidas de la misma persona
# o del mismo tipo de rechazo mientras permanece frente a la cámara.
# El primer evento se registra inmediatamente y los repetidos quedan
# limitados a uno por minuto.
INTERVALO_MINIMO_EVENTOS = 60
_ultimo_evento_por_clave = {}
_eventos_lock = Lock()


# ------------------------------------------------------------------
# FUNCIÓN UTILIZADA POR EL RESTO DEL PROGRAMA
# ------------------------------------------------------------------

def registrar_evento_supabase(
    resultado,
    persona_id=None,
    similitud=None,
    antispoof=None,
    deteccion=None,
):
    """
    Prepara un evento y lo coloca en la cola.

    resultado debe ser alguno de estos valores:

    - "authorized"
    - "denied"
    - "spoof"

    Los demás campos son opcionales porque no todos los eventos
    tienen la misma información.
    """

    resultados_validos = {
        "authorized",
        "denied",
        "spoof",
    }

    if resultado not in resultados_validos:
        raise ValueError(
            f"Resultado no permitido: {resultado}"
        )

    # Crear el diccionario que después se enviará a Supabase.
    evento = {
        "result": resultado,

        # Solo existe cuando se reconoció una persona.
        "person_id": persona_id,

        # Puntaje obtenido por SFace.
        "similarity": (
            float(similitud)
            if similitud is not None
            else None
        ),

        # Puntaje obtenido por el modelo antispoofing.
        "antispoof": (
            float(antispoof)
            if antispoof is not None
            else None
        ),

        # Confianza con la que YuNet detectó el rostro.
        "detection": (
            float(deteccion)
            if deteccion is not None
            else None
        ),
    }

    # Eliminar los valores None.
    #
    # Por ejemplo, un spoof no tiene persona_id ni similarity.
    # El evento resultante podría quedar así:
    #
    # {
    #     "result": "spoof",
    #     "antispoof": 0.17
    # }
    evento = {
        clave: valor
        for clave, valor in evento.items()
        if valor is not None
    }

    # Agrupar por resultado y persona. Los rechazos y spoof, que no
    # tienen persona_id, se limitan independientemente por resultado.
    clave_evento = (
        resultado,
        persona_id,
    )
    ahora = time.monotonic()

    with _eventos_lock:
        ultimo_evento = _ultimo_evento_por_clave.get(
            clave_evento
        )

        if (
            ultimo_evento is not None
            and ahora - ultimo_evento
            < INTERVALO_MINIMO_EVENTOS
        ):
            return False

        _ultimo_evento_por_clave[clave_evento] = ahora

    # Colocar el evento en la cola.
    #
    # Esta operación es rápida y no espera una respuesta de internet.
    eventos_supabase_queue.put(evento)
    return True


# ------------------------------------------------------------------
# CONEXIÓN CON SUPABASE
# ------------------------------------------------------------------

def crear_cliente():
    """
    Crea una conexión autenticada para la Raspberry.

    Se utiliza la clave publicable y el usuario creado en
    Authentication, no la clave administrativa de Supabase.
    """

    # Leer las variables de app/.env.
    credenciales = dotenv_values(RUTA_ENV)

    # Lista de variables obligatorias.
    variables = (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_DEVICE_EMAIL",
        "SUPABASE_DEVICE_PASSWORD",
    )

    # Comprobar cuáles faltan o están vacías.
    faltantes = [
        nombre
        for nombre in variables
        if not credenciales.get(nombre)
    ]

    if faltantes:
        raise RuntimeError(
            "Faltan variables en app/.env: "
            + ", ".join(faltantes)
        )

    # Crear el cliente usando la dirección del proyecto
    # y la clave publicable.
    cliente = create_client(
        credenciales["SUPABASE_URL"],
        credenciales["SUPABASE_PUBLISHABLE_KEY"],
    )

    # Iniciar sesión con el usuario de la Raspberry.
    #
    # Después de iniciar sesión, Supabase aplica las políticas RLS
    # correspondientes al rol "authenticated".
    cliente.auth.sign_in_with_password({
        "email": credenciales["SUPABASE_DEVICE_EMAIL"],
        "password": credenciales["SUPABASE_DEVICE_PASSWORD"],
    })

    return cliente


# ------------------------------------------------------------------
# ENVÍO DE UN EVENTO
# ------------------------------------------------------------------

def enviar_evento(cliente, evento):
    """
    Inserta un evento en la tabla access_events.

    Esta función puede lanzar una excepción si:
    - no hay internet;
    - Supabase está caído;
    - venció la sesión;
    - las políticas RLS no permiten la operación.
    """

    (
        cliente
        .table("access_events")
        .insert(
            evento,

            # La Raspberry no necesita recibir nuevamente
            # la fila después de insertarla.
            returning="minimal",
        )
        .execute()
    )


# ------------------------------------------------------------------
# RESPALDO LOCAL
# ------------------------------------------------------------------

def guardar_evento_pendiente(evento):
    """
    Agrega un evento al archivo local.

    Se utiliza cuando no fue posible enviarlo a Supabase.
    El modo "a" agrega contenido sin borrar los eventos anteriores.
    """

    # Crear la carpeta data si no existiera.
    RUTA_EVENTOS_PENDIENTES.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Abrir el archivo en modo append.
    with RUTA_EVENTOS_PENDIENTES.open(
        "a",
        encoding="utf-8",
    ) as archivo:

        # Convertir el diccionario a JSON y agregar un salto de línea.
        archivo.write(
            json.dumps(
                evento,
                ensure_ascii=False,
            )
            + "\n"
        )


def leer_eventos_pendientes():
    """
    Lee todos los eventos guardados localmente.

    Devuelve una lista de diccionarios.
    """

    # Si el archivo no existe, no hay eventos pendientes.
    if not RUTA_EVENTOS_PENDIENTES.exists():
        return []

    eventos = []

    # Leer el contenido y separarlo por líneas.
    lineas = RUTA_EVENTOS_PENDIENTES.read_text(
        encoding="utf-8"
    ).splitlines()

    for linea in lineas:

        # Ignorar líneas vacías.
        if not linea.strip():
            continue

        # Convertir el texto JSON nuevamente en un diccionario.
        eventos.append(
            json.loads(linea)
        )

    return eventos


def guardar_lista_pendientes(eventos):
    """
    Reemplaza el archivo por la lista de eventos recibida.

    Se usa después de una sincronización para eliminar los eventos
    que ya llegaron a Supabase y conservar los que fallaron.
    """

    # Si no quedan eventos, eliminar el archivo.
    if not eventos:
        if RUTA_EVENTOS_PENDIENTES.exists():
            RUTA_EVENTOS_PENDIENTES.unlink()

        return

    # Escribir primero en un archivo temporal evita dejar un archivo
    # incompleto si el sistema se apaga durante la escritura.
    ruta_temporal = (
        RUTA_EVENTOS_PENDIENTES
        .with_suffix(".tmp")
    )

    # Convertir cada evento en una línea JSON.
    contenido = "".join(
        json.dumps(
            evento,
            ensure_ascii=False,
        )
        + "\n"
        for evento in eventos
    )

    ruta_temporal.write_text(
        contenido,
        encoding="utf-8",
    )

    # Reemplazar el archivo anterior por el temporal.
    ruta_temporal.replace(
        RUTA_EVENTOS_PENDIENTES
    )


# ------------------------------------------------------------------
# SINCRONIZACIÓN DE EVENTOS PENDIENTES
# ------------------------------------------------------------------

def sincronizar_pendientes(cliente):
    """
    Intenta enviar todos los eventos guardados localmente.

    Los eventos se envían en el mismo orden en que ocurrieron.
    Si uno falla, se conserva ese evento y todos los posteriores.
    """

    eventos = leer_eventos_pendientes()

    for indice, evento in enumerate(eventos):
        try:
            enviar_evento(
                cliente,
                evento,
            )

        except Exception:
            # Conservar el evento que falló y los siguientes.
            guardar_lista_pendientes(
                eventos[indice:]
            )

            # Volver a lanzar el error para que el worker sepa
            # que perdió la conexión.
            raise

    # Si todos se enviaron, eliminar el archivo pendiente.
    guardar_lista_pendientes([])


# ------------------------------------------------------------------
# WORKER PRINCIPAL
# ------------------------------------------------------------------

def supabase_worker(sincronizacion):
    """
    Procesa la cola de eventos en un hilo independiente.

    sincronizacion.shutdown es el Event que indica que SmartGate
    debe finalizar.
    """

    # El cliente comienza vacío y se crea cuando haga falta.
    cliente = None

    # Se utiliza para no intentar reconectar continuamente.
    ultimo_reintento = 0.0

    # Continuar mientras:
    # - SmartGate siga encendido; o
    # - todavía queden eventos en la cola de memoria.
    while (
        not sincronizacion.shutdown.is_set()
        or not eventos_supabase_queue.empty()
    ):
        try:
            # Esperar como máximo un segundo por un evento.
            #
            # Esta espera bloqueada evita un bucle que consuma
            # procesador innecesariamente.
            evento = eventos_supabase_queue.get(
                timeout=1
            )

        except Empty:
            # No llegó ningún evento durante ese segundo.
            evento = None

        # monotonic mide tiempo transcurrido y no se altera aunque
        # cambie la fecha o la hora del sistema.
        ahora = time.monotonic()

        # Si existe un archivo pendiente, intentar sincronizarlo
        # cada diez segundos.
        debe_reintentar = (
            RUTA_EVENTOS_PENDIENTES.exists()
            and ahora - ultimo_reintento >= 10
        )

        # Si no hay evento nuevo ni corresponde reintentar,
        # volver a esperar.
        if evento is None and not debe_reintentar:
            continue

        try:
            # Crear o recuperar una conexión.
            if cliente is None:
                cliente = crear_cliente()

            # Primero enviar los eventos antiguos.
            sincronizar_pendientes(cliente)

            # Después enviar el evento nuevo.
            if evento is not None:
                enviar_evento(
                    cliente,
                    evento,
                )

        except Exception as error:
            # Si el evento nuevo no pudo enviarse,
            # guardarlo en el archivo local.
            if evento is not None:
                guardar_evento_pendiente(
                    evento
                )

            # Descartar el cliente actual.
            # En el próximo intento se iniciará una sesión nueva.
            cliente = None

            # Recordar cuándo ocurrió el último intento.
            ultimo_reintento = ahora

            # Informar el problema sin detener SmartGate.
            print(
                "Evento guardado localmente:",
                error,
            )
