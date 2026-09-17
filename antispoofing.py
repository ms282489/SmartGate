"""Modulo 2: prueba de vida con MiniFASNetV2."""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


class EvaluadorAntispoofing:
    """Prepara el recorte facial y ejecuta MiniFASNetV2 en CPU."""

    def __init__( self, ruta_modelo: Path, escala_recorte: float,  hilos_intra: int = 2, hilos_inter: int = 1,) -> None:
        #None significa que no retorna nada la funcion
        opciones = ort.SessionOptions()         # SessionOptions permite controlar cuantos hilos internos utiliza ONNX
        opciones.intra_op_num_threads = hilos_intra     #Hilos usados en operaciones de este modelo
        opciones.inter_op_num_threads = hilos_inter     #Hilos usados para opreaciones en paralelo

         # Se carga el archivo ONNX una sola vez y se fuerza el uso de CPU.
        self._sesion = ort.InferenceSession( str(ruta_modelo), sess_options=opciones,providers=["CPUExecutionProvider"],)


         # El nombre de entrada puede cambiar entre exportaciones del modelo. Se
        # obtiene del propio archivo en vez de escribirlo manualmente.
        self._nombre_entrada = self._sesion.get_inputs()[0].name

        # Guardamos la ampliacion que se aplicara alrededor de cada rostro.
        self._escala_recorte = escala_recorte


    def evaluar(self, imagen: np.ndarray, rostro: np.ndarray) -> float:
        """Devuelve la puntuacion de la clase `rostro real` entre 0 y 1."""
        #Yunet devuelve una variable array rostro la cual tiene muchos datos de el mismo, por lo que en este caso se van a tomar los 4 primeros
        # Dimensiones de la imagen completa.
        alto, ancho = imagen.shape[:2]

        # YuNet entrega primero: x, y, ancho de cara y alto de cara.
        x, y, w, h = map(int, rostro[:4])

        # Un rectangulo sin area no se puede analizar y se rechaza directamente.
        if w <= 0 or h <= 0:
            return 0.0

        # MiniFASNetV2 necesita ver parte del contexto que rodea la cara. La
        # escala tambien se limita para que el recorte no exceda la imagen.
        escala = min(self._escala_recorte,(ancho - 1) / w,(alto - 1) / h,)

        # Centro del rectangulo detectado por YuNet.
        centro_x = x + w / 2
        centro_y = y + h / 2

        # Coordenadas del recorte ampliado. max() y min() impiden salir fuera de
        # los limites de la imagen.
        izquierda = max(0, int(centro_x - w * escala / 2))
        derecha = min(ancho - 1, int(centro_x + w * escala / 2))
        arriba = max(0, int(centro_y - h * escala / 2))
        abajo = min(alto - 1, int(centro_y + h * escala / 2))

        # En NumPy se recorta como imagen[filas, columnas]. Se suma 1 porque el
        # extremo final de un slice no se incluye automaticamente.
        recorte = imagen[arriba : abajo + 1, izquierda : derecha + 1]
        if recorte.size == 0:
            return 0.0

        # Esta exportacion concreta de MiniFASNetV2 espera 80 x 80, valores
        # float32, rango 0-255 y canales en orden BGR.
        cara = cv2.resize(recorte, (80, 80)).astype(np.float32)

        # OpenCV usa alto x ancho x canales. ONNX espera un lote con la forma:
        # cantidad x canales x alto x ancho, es decir 1 x 3 x 80 x 80.
        tensor = np.ascontiguousarray(cara.transpose(2, 0, 1)[None])

        # El primer None significa "devolver todas las salidas del modelo". No
        # indica un error. El diccionario relaciona el nombre de entrada con el
        # tensor preparado arriba.
        salida = self._sesion.run(None,{self._nombre_entrada: tensor},)[0].reshape(-1)

        # Esta version debe devolver tres numeros validos. Cualquier otro
        # resultado se trata como no confiable y recibe puntuacion cero.
        if salida.size != 3 or not np.isfinite(salida).all():
            return 0.0

        # Softmax transforma las tres salidas en puntuaciones que suman uno.
        # Restar el maximo evita desbordamientos numericos al usar exp().
        puntuaciones = np.exp(salida - salida.max())
        puntuaciones /= puntuaciones.sum()

        # En el modelo provisto, el indice 1 representa una cara real.
        return float(puntuaciones[1])
