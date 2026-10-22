"""Buffers compartidos por los modelos."""

from queue import Queue


# Buffer utilizado por el modelo de antispoofing
buffer1 = Queue(maxsize=1)

# Buffer utilizado por el modelo de reconocimiento
buffer2 = Queue(maxsize=1)


def guardar_muestras(
    muestra_antispoof,
    muestra_reconocimiento,
):
    """Guarda las dos muestras generadas por detección."""

    buffer1.put(muestra_antispoof)
    buffer2.put(muestra_reconocimiento)


def tomar_buffer1():
    """Obtiene y elimina la muestra de antispoofing."""

    return buffer1.get()


def tomar_buffer2():
    """Obtiene y elimina la muestra de reconocimiento."""

    return buffer2.get()


def limpiar_buffers():
    """Elimina las muestras que todavía estén guardadas."""

    if not buffer1.empty():
        buffer1.get_nowait()

    if not buffer2.empty():
        buffer2.get_nowait()