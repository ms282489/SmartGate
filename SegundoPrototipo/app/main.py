import threading



from Tareas.GPIO import gpio_manager #Tarea creadora de GPIO



#Crear hilos

gpio_hilo = threading.Thread(target=gpio_manager.gpio_manager, name="gpio_manager")





#Iniciae hilos
gpio_hilo.start()