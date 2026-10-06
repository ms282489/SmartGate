from queue import Queue


# Cola utilizada para enviar órdenes al worker de GPIO
gpio_comando_queue = Queue()


def signal_activo():
    """Solicita encender el LED de sistema activo."""

    gpio_comando_queue.put("ACTIVO")


def signal_procesando():
    """Solicita encender el LED de procesamiento."""

    gpio_comando_queue.put("PROCESANDO")


def signal_aceptado():
    """Solicita encender el LED de acceso aceptado."""

    gpio_comando_queue.put("ACEPTADO")


def signal_rechazado():
    """Solicita encender el LED de acceso rechazado."""

    gpio_comando_queue.put("RECHAZADO")


def signal_abrir_porton():
    """Solicita generar el pulso de apertura del portón."""

    gpio_comando_queue.put("ABRIR")