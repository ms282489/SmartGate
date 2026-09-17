"""Modulo 3: extraccion y comparacion de identidad con SFace."""

from pathlib import Path

import cv2
import numpy as np


class ReconocedorFacial:
    """Carga SFace y ofrece las operaciones necesarias para reconocer caras."""

    def __init__(self, ruta_modelo: Path) -> None:
        # Carga SFace una sola vez. ``-> None`` indica que el constructor no
        # devuelve un valor: solamente deja listo el objeto.
        self._reconocedor = cv2.FaceRecognizerSF.create(str(ruta_modelo), "",)

    def obtener_embedding(self, imagen: np.ndarray, rostro: np.ndarray,) -> np.ndarray:
        """Alinea la cara y la transforma en un vector numerico."""
        # alignCrop utiliza los puntos de ojos, nariz y boca entregados por
        # YuNet. Asi corrige inclinacion, posicion y escala de la cara.
        cara_alineada = self._reconocedor.alignCrop(imagen, rostro)

        # feature convierte la cara alineada en un embedding: un vector que
        # representa sus caracteristicas y permite comparar identidades.
        return self._reconocedor.feature(cara_alineada)

    def comparar(self, embedding_referencia: np.ndarray,embedding_actual: np.ndarray,) -> float:
        """Devuelve la similitud coseno entre dos embeddings."""
        # FR_COSINE selecciona similitud coseno. Cuanto mayor sea el resultado,
        # mas semejantes son las dos representaciones faciales.
        return float(self._reconocedor.match(embedding_referencia, embedding_actual, cv2.FaceRecognizerSF_FR_COSINE,))
