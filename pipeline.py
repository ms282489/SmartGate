"""
Pipeline de SmartGate.

Este archivo coordina los tres modelos:

1. Detección de la cara con YuNet.
2. Antispoofing con MiniFASNetV2.
3. Reconocimiento facial con SFace.

Cada modelo se ejecuta como una tarea dentro de un hilo.
"""

import math

# ThreadPoolExecutor administra automáticamente un grupo de hilos.
# No tenemos que crear los hilos manualmente.
from concurrent.futures import ThreadPoolExecutor


class PipelineProcesamiento:
    """
    Clase encargada de ejecutar los tres modelos en el orden correcto.
    """

    def __init__(
        self,
        detector,
        antispoofing,
        reconocedor,
        embedding_referencia,
        umbral_antispoof,
        umbral_identidad,
    ):
        """
        Guardar los modelos y valores necesarios.

        Este constructor no ejecuta los modelos.
        Solamente prepara el pipeline.
        """

        # Módulo encargado de detectar caras con YuNet.
        self.detector = detector

        # Módulo encargado de comprobar que la cara sea real.
        self.antispoofing = antispoofing

        # Módulo encargado de comparar identidades con SFace.
        self.reconocedor = reconocedor

        # Vector facial de la persona autorizada.
        # Se calcula una sola vez al iniciar SmartGate.
        self.embedding_referencia = embedding_referencia

        # Puntuación mínima para considerar que la cara es real.
        self.umbral_antispoof = umbral_antispoof

        # Similitud mínima para autorizar a la persona.
        self.umbral_identidad = umbral_identidad

        # Inicialmente todavía no existe el grupo de hilos.
        self.ejecutor = None

    def iniciar(self):
        """
        Crear el grupo de hilos.

        max_workers=3 significa que puede haber hasta tres hilos
        disponibles para ejecutar las tareas.
        """

        # Evitar crear dos grupos de hilos si iniciar()
        # se llama accidentalmente más de una vez.
        if self.ejecutor is None:
            self.ejecutor = ThreadPoolExecutor(max_workers=3)

    def procesar(self, imagen):
        """
        Procesar una imagen completa.

        La imagen pasa por las etapas en este orden:

        detección -> antispoofing -> reconocimiento
        """

        # No se puede procesar antes de llamar pipeline.iniciar().
        if self.ejecutor is None:
            raise RuntimeError("La tuberia no esta iniciada")

        # Resultado inicial.
        #
        # Los valores se irán completando a medida que la imagen
        # pase por las diferentes etapas.
        resultado = {
            "estado": "Sin rostro",
            "coincide": False,
            "antispoof": None,
            "similitud": None,
        }

        # =====================================================
        # ETAPA 1: DETECCIÓN FACIAL CON YUNET
        # =====================================================

        # submit() envía una función para que sea ejecutada
        # por uno de los hilos del ThreadPoolExecutor.
        #
        # Es equivalente a ejecutar:
        #
        # rostros = self.detector.detectar(imagen)
        #
        # pero la función se ejecuta dentro de un hilo.
        tarea_deteccion = self.ejecutor.submit(self.detector.detectar, imagen,)
 
        # result() espera a que la tarea termine y obtiene
        # el valor devuelto por detector.detectar().
        rostros = tarea_deteccion.result()

        # Si no se encontró ninguna cara, el resultado conserva
        # el estado inicial "Sin rostro".
        if len(rostros) == 0:
            return resultado

        # SmartGate procesa una sola persona por vez.
        if len(rostros) > 1:
            resultado["estado"] = "Hay varias caras"
            return resultado

        # Si llegamos hasta aquí, existe exactamente una cara.
        rostro = rostros[0]

        # =====================================================
        # ETAPA 2: ANTISPOOFING CON MINIFASNETV2
        # =====================================================

        # Enviar el método evaluar() como una nueva tarea.
        #
        # El método recibe:
        # - La imagen completa.
        # - La información de la cara encontrada por YuNet.
        tarea_antispoof = self.ejecutor.submit(self.antispoofing.evaluar, imagen, rostro, )

        # Esperar la puntuación entregada por MiniFASNetV2.
        puntuacion = tarea_antispoof.result()

        # Guardar la puntuación en el resultado.
        resultado["antispoof"] = puntuacion

        # Si la puntuación no alcanza el umbral, la cara
        # se considera falsa o poco confiable.
        if puntuacion < self.umbral_antispoof:
            resultado["estado"] = "No supera el antispoofing"
            return resultado

        # Si superó el umbral, puede pasar al reconocimiento.

        # =====================================================
        # ETAPA 3: RECONOCIMIENTO FACIAL CON SFACE
        # =====================================================

        # Primero convertir la cara capturada en un embedding.
        #
        # Un embedding es un vector numérico que representa
        # las características de una cara.
        tarea_embedding = self.ejecutor.submit(self.reconocedor.obtener_embedding, imagen, rostro, )

        # Esperar y obtener el embedding de la cara actual.
        embedding_actual = tarea_embedding.result()

        # Enviar otra tarea para comparar:
        #
        # - El embedding de la persona registrada.
        # - El embedding de la persona capturada.
        tarea_comparacion = self.ejecutor.submit(self.reconocedor.comparar, self.embedding_referencia, embedding_actual,)

        # Esperar el resultado de la comparación.
        similitud = tarea_comparacion.result()

        # Guardar la similitud en el resultado.
        resultado["similitud"] = similitud

        # math.isfinite() comprueba que la similitud sea
        # un número válido, evitando valores como NaN o infinito.
        similitud_valida = math.isfinite(similitud)

        # Autorizar solamente cuando:
        #
        # 1. La similitud sea un número válido.
        # 2. La similitud alcance el umbral configurado.
        if (
            similitud_valida
            and similitud >= self.umbral_identidad
        ):
            resultado["estado"] = (
                "Coincide con la persona registrada"
            )
            resultado["coincide"] = True

        # Si no alcanza el umbral, es una persona desconocida.
        else:
            resultado["estado"] = "Persona desconocida"

        # Entregar el resultado terminado a main.py.
        return resultado

    def detener(self):
        """
        Cerrar ordenadamente el grupo de hilos.
        """

        # Comprobar que el ejecutor haya sido creado.
        if self.ejecutor is not None:

            # shutdown(wait=True) deja de aceptar nuevas tareas
            # y espera a que terminen las tareas pendientes.
            self.ejecutor.shutdown(wait=True)

            # Volver a None permite saber que el pipeline
            # ya no está funcionando.
            self.ejecutor = None