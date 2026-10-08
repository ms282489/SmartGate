from queue import Queue
from threading import Thread

import yaml

from core.pipeline_manager import ejecutar_pipeline
from core.sync import create_synchronization
from Tareas.GPIO.gpio_manager import gpio_manager
from Tareas.antispoof.antispoof_worker import antispoof_worker
from Tareas.deteccion.deteccion_worker import deteccion_worker
from Tareas.reconocimiento.reconocimiento_worker import (
    reconocimiento_worker,
)

# Leer la configuración
with open(
    "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)


# Crear los recursos compartidos
sincronizacion = create_synchronization()
cola_mensajes = Queue()


# Configurar e iniciar GPIO
gpio_manager(
    config["gpio"],
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
    ),
    name="Antispoof",
)

reconocimiento_thread = Thread(
    target=reconocimiento_worker,
    args=(
        config,
        sincronizacion,
        cola_mensajes,
    ),
    name="Reconocimiento",
)


# Iniciar los modelos
deteccion_thread.start()
antispoof_thread.start()
reconocimiento_thread.start()

# Ejecutar el control principal
ejecutar_pipeline(
    sincronizacion,
    cola_mensajes,
)

# Esperar que los modelos terminen
deteccion_thread.join()
antispoof_thread.join()
reconocimiento_thread.join()
