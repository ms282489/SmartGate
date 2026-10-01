import threading
from config import yaml
from Tareas.GPIO import gpio_manager #Tarea creadora de GPIO


# Importar de yaml
with open("config/config.yaml", "r") as file:
    config = yaml.safe_load(file)
gpio_config = config["gpio"]    


# Crear hilos
gpio_thread = threading.Thread(
    target=gpio_manager,
    args=(gpio_config,),
    name="GPIO"
)




# Iniciar hilos
gpio_thread.start()