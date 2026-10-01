"""Configuracion central de SmartGate.

Los valores conservan la configuracion del programa original. Este es el unico
archivo que hay que editar para cambiar rutas, umbrales o la camara.
"""

from pathlib import Path


# ``__file__`` es la ruta de este archivo. Con ``resolve().parent`` obtenemos
# la carpeta del proyecto, aunque se ejecute el programa desde otro directorio.
CARPETA_PROYECTO = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Archivos utilizados por los tres modelos
# ---------------------------------------------------------------------------
# La referencia contiene la unica persona autorizada en esta version.
RUTA_REFERENCIA = CARPETA_PROYECTO / "test.jpeg"

# YuNet: localiza una o varias caras dentro de la imagen.
RUTA_DETECTOR = (
    CARPETA_PROYECTO / "models" / "face_detection_yunet_2023mar.onnx"
)

# MiniFASNetV2: determina si la cara parece real o es una suplantacion.
RUTA_ANTISPOOF = CARPETA_PROYECTO / "models" / "MiniFASNetV2.onnx"

# SFace: convierte la cara en un vector y lo compara con la referencia.
RUTA_RECONOCEDOR = (
    CARPETA_PROYECTO / "models" / "face_recognition_sface_2021dec.onnx"
)

# ---------------------------------------------------------------------------
# Camara y frecuencia de procesamiento
# ---------------------------------------------------------------------------
# Cero selecciona normalmente la primera camara conectada al equipo.
INDICE_CAMARA = 0

# Resolucion solicitada a la camara. La camara puede entregar otra resolucion
# si no admite exactamente estos valores.
ANCHO = 640
ALTO = 480

# Espera entre un resultado y la captura siguiente.
PAUSA_SEGUNDOS = 0.3

# Tiempo inicial para que la exposicion de la camara se estabilice.
TIEMPO_ESTABILIZACION_CAMARA = 2.0

# ---------------------------------------------------------------------------
# Umbrales de decision
# ---------------------------------------------------------------------------
# Confianza minima para que YuNet acepte una deteccion como cara.
UMBRAL_DETECCION = 0.85

# Puntuacion minima para considerar que la cara es real.
UMBRAL_ANTISPOOF = 0.90

# Similitud coseno minima para considerar que es la persona registrada.
UMBRAL_IDENTIDAD = 0.50

# MiniFASNetV2 necesita contexto alrededor de la cara.
ESCALA_RECORTE = 2.7

# Limites iniciales adecuados para una Raspberry Pi 4.
# Estos valores evitan que las bibliotecas intenten ocupar todos los nucleos.
HILOS_OPENCV = 2
HILOS_ONNX_INTRA = 2
HILOS_ONNX_INTER = 1
