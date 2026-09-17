"""Modulo 1: deteccion de rostros con YuNet."""

from pathlib import Path
from typing import List, Sequence

import cv2
import numpy as np


class DetectorRostros:
    """Carga YuNet una vez y detecta rostros en imagenes BGR."""

    def __init__(self, ruta_modelo: Path, tamano_inicial: Sequence[int], umbral_deteccion: float,) -> None:
        # ``-> None`` indica que __init__ configura el objeto, pero no devuelve
        # un resultado. El objeto creado queda guardado por quien llama la clase.
        # El modelo se carga una sola vez al iniciar SmartGate, no por fotograma.
        self._detector = cv2.FaceDetectorYN.create(str(ruta_modelo), "", tuple(tamano_inicial), score_threshold=umbral_deteccion,)
            # OpenCV necesita la ruta en forma de texto, por eso se usa str().
            # Este argumento permite indicar configuracion adicional. YuNet no
            # la necesita, por lo que se pasa una cadena vacia.
           
        
    def detectar(self, imagen: np.ndarray) -> List[np.ndarray]:
        """Devuelve las caras detectadas o una lista vacia."""
        # OpenCV guarda la forma como (alto, ancho, canales). Solo necesitamos
        # los primeros dos valores para informar el tamano real al detector.
        alto, ancho = imagen.shape[:2]

        # La foto de referencia y la camara pueden tener resoluciones distintas.
        self._detector.setInputSize((ancho, alto))

        # detect() devuelve dos elementos. El primero no se usa; por convencion
        # se lo llama ``_``. El segundo contiene las caras detectadas.
        _, rostros = self._detector.detect(imagen)

        # OpenCV devuelve None cuando no encuentra ninguna cara. El resto del
        # sistema trabaja con listas, por lo que lo convertimos en lista vacia.
        if rostros is None:
            return []

        # Cada elemento contiene caja facial, cinco puntos faciales y confianza.
        return list(rostros)
