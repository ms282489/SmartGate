from core.sync import gate_closed
import gpiod    

def fc_worker(fc_request):

    while True:


        # El hilo queda bloqueado esperando un evento del GPIO
        fc_request.wait_edge_events()

        # Leer los eventos pendientes
        eventos = fc_request.read_edge_events()

        for evento in eventos:

            # LOW -> HIGH
            # El portón dejó la posición de cerrado
            if evento.event_type == gpiod.EdgeEvent.Type.RISING_EDGE:
                gate_closed.clear()

            # HIGH -> LOW
            # El portón llegó a cerrado
            elif evento.event_type == gpiod.EdgeEvent.Type.FALLING_EDGE:
                gate_closed.set()
