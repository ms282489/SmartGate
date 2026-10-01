import threading
import queue
import time
import gpiod

from gpio_comandos import gpio_comando_queue
from core.sync import gate_closed

#hilo de manejo de pines gpio

def gpio_manager(config):

    chip = config["chip"]

    pin_fc = config["pins"]["final_carrera"]

    pin_led_activo = config["pins"]["led_activo"]
    pin_led_procesando = config["pins"]["led_procesando"]
    pin_led_aceptado = config["pins"]["led_aceptado"]
    pin_led_rechazado = config["pins"]["led_rechazado"]

    pin_abrir = config["pins"]["abrir_porton"]

    pulse_tiempo = config["gate"]["pulse_tiempo"]