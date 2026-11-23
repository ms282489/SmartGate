import signal
from pathlib import Path
from queue import Queue
from threading import Thread

import yaml

from core.metricas import medidor
from core.pipeline_manager import ejecutar_pipeline
from core.sync import create_synchronization
from core.states import MensajePipeline
from core.vista_camara import (
    VistaCamaraCompartida,
    ejecutar_vista_camara,
)
from Tareas.GPIO.gpio_manager import gpio_manager
from Tareas.antispoof.antispoof_worker import antispoof_worker
from Tareas.deteccion.deteccion_worker import deteccion_worker
from Tareas.reconocimiento.reconocimiento_worker import (
    reconocimiento_worker,
)
from Tareas.reconocimiento.galeria import (
    cargar_respaldo_local,
    galeria_compartida,
)
from Tareas.supabase.supabase_worker import (
    supabase_worker,
)
from Tareas.supabase.galeria_worker import (
    galeria_supabase_worker,
)
from Tareas.telemetria.telemetria_worker import (
    telemetria_worker,
)


CARPETA_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CONFIG = CARPETA_PROYECTO / "config" / "config.yaml"


# Leer la configuración
with RUTA_CONFIG.open("r", encoding="utf-8") as archivo:
    config = yaml.safe_load(archivo)

# Medición opcional de tiempos del pipeline (sección `metricas`).
medidor.configurar(config)


# Cargar la última galería persistente antes de iniciar cualquier hilo. Así el
# primer reconocimiento no depende de Internet y Supabase puede comparar su
# estado real contra el respaldo, incluso cuando la base no contiene personas.
personas_locales = cargar_respaldo_local()
galeria_compartida.reemplazar(personas_locales)
print(
    "Galería facial local cargada:",
    len(personas_locales),
    "personas",
)


# Crear los recursos compartidos
sincronizacion = create_synchronization()
cola_mensajes = Queue()
vista_camara = VistaCamaraCompartida()
vista_camara.actualizar_supabase(False, len(personas_locales))


def solicitar_apagado(_numero_senal=None, _frame=None):
    """Solicita un cierre ordenado desde systemd o desde la terminal."""

    if not sincronizacion.shutdown.is_set():
        cola_mensajes.put(MensajePipeline.APAGAR)


signal.signal(signal.SIGINT, solicitar_apagado)
signal.signal(signal.SIGTERM, solicitar_apagado)


# Configurar e iniciar GPIO
gpio_manager(
    config,
    sincronizacion,
    cola_mensajes,
)


# Crear el hilo de detección
deteccion_thread = Thread(
    target=deteccion_worker,
    args=(
        config,
        sincronizacion,
        cola_mensajes,
        vista_camara,
    ),
    name="Deteccion",
)


# Crear el hilo de antispoofing
antispoof_thread = Thread(
    target=antispoof_worker,
    args=(
        config,
        sincronizacion,
        cola_mensajes,
        vista_camara,
    ),
    name="Antispoof",
)


# Crear el hilo de reconocimiento
reconocimiento_thread = Thread(
    target=reconocimiento_worker,
    args=(
        config,
        sincronizacion,
        cola_mensajes,
        vista_camara,
    ),
    name="Reconocimiento",
)


# Crear el hilo de telemetría
telemetria_thread = Thread(
    target=telemetria_worker,
    args=(
        config,
        sincronizacion,
    ),
    name="Telemetria",
)


# Crear el hilo de Supabase
supabase_thread = Thread(
    target=supabase_worker,
    args=(
        config,
        sincronizacion,
    ),
    name="EventosSupabase",
)


# La galería facial se sincroniza aparte. Si Internet falla, este hilo
# reintenta sin detener detección, antispoofing ni reconocimiento.
galeria_thread = Thread(
    target=galeria_supabase_worker,
    args=(
        config,
        sincronizacion,
        vista_camara,
    ),
    name="GaleriaSupabase",
)


# El gestor del pipeline corre aparte para reservar el hilo principal para
# la interfaz gráfica, como requiere OpenCV en la Raspberry.
pipeline_thread = Thread(
    target=ejecutar_pipeline,
    args=(
        sincronizacion,
        cola_mensajes,
        config,
        vista_camara,
    ),
    name="Pipeline",
)


# Iniciar los workers
deteccion_thread.start()
antispoof_thread.start()
reconocimiento_thread.start()
telemetria_thread.start()
supabase_thread.start()
galeria_thread.start()
pipeline_thread.start()


# Mostrar la cámara si está habilitada. Si no existe una sesión gráfica,
# la función informa el problema y el control de acceso sigue funcionando.
preview_config = config.get("camera", {}).get("preview", {})

if preview_config.get("enabled", False):
    ejecutar_vista_camara(
        vista_camara,
        sincronizacion,
        cola_mensajes,
        preview_config,
    )


# Sin ventana, o después de cerrarla, esperar que finalice el pipeline.
pipeline_thread.join()


# Esperar que los workers terminen
deteccion_thread.join()
antispoof_thread.join()
reconocimiento_thread.join()
telemetria_thread.join()
supabase_thread.join()
galeria_thread.join()

# Guardar las mediciones de YuNet que todavía estén en memoria.
medidor.cerrar_archivos()
