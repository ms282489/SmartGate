import threading
import queue
import time
import gpiod

from gpio_comandos import gpio_comando_queue
from core.sync import gate_closed

#hilo de manejo de pines gpio

