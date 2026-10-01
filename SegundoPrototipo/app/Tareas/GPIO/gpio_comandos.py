import queue

gpio_comando_queue = queue.Queue()

def signal_activo():
    gpio_comando_queue.put("ACTIVO")

def signal_procesando():
    gpio_comando_queue.put("PROCESANDO")

def signal_aceptado():
    gpio_comando_queue.put("ACEPTADO")     

def signal_rechazado():
    gpio_comando_queue.put("RECHAZADO")

def signal_abrir_porton():
    gpio_comando_queue.put("ABRIR_PORTON")

