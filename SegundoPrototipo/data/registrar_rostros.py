"""Genera los embeddings de las personas autorizadas."""

import os

import cv2
import numpy as np
import yaml


RUTA_DETECTOR = (
    "app/Tareas/deteccion/"
    "face_detection_yunet_2023mar.onnx"
)

RUTA_RECONOCEDOR = (
    "app/Tareas/reconocimiento/"
    "face_recognition_sface_2021dec.onnx"
)

CARPETA_PERSONAS = "data/personas_autorizadas"
RUTA_EMBEDDINGS = "data/embeddings.npy"


# Leer la configuración
with open(
    "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)


umbral_deteccion = config["thresholds"]["detection"]


# Cargar los modelos
detector = cv2.FaceDetectorYN.create(
    RUTA_DETECTOR,
    "",
    (320, 320),
    umbral_deteccion,
    0.3,
    5000,
)

reconocedor = cv2.FaceRecognizerSF.create(
    RUTA_RECONOCEDOR,
    "",
)


embeddings = []


# Leer las imágenes de las personas autorizadas
for nombre_archivo in os.listdir(CARPETA_PERSONAS):

    if not nombre_archivo.lower().endswith(
        (".jpg", ".jpeg", ".png")
    ):
        continue

    ruta_imagen = os.path.join(
        CARPETA_PERSONAS,
        nombre_archivo,
    )

    imagen = cv2.imread(ruta_imagen)

    if imagen is None:
        print("No se pudo leer:", nombre_archivo)
        continue

    detector.setInputSize(
        (imagen.shape[1], imagen.shape[0])
    )

    resultado, rostros = detector.detect(imagen)

    if rostros is None:
        print("No se encontró un rostro:", nombre_archivo)
        continue

    # Utilizar el primer rostro encontrado
    rostro_detectado = rostros[0]

    rostro_alineado = reconocedor.alignCrop(
        imagen,
        rostro_detectado,
    )

    embedding = reconocedor.feature(
        rostro_alineado
    )

    embeddings.append(embedding[0])

    print("Rostro registrado:", nombre_archivo)


# Guardar los embeddings
if len(embeddings) > 0:

    embeddings = np.array(
        embeddings,
        dtype=np.float32,
    )

    np.save(
        RUTA_EMBEDDINGS,
        embeddings,
    )

    print("Embeddings guardados en:", RUTA_EMBEDDINGS)

else:
    print("No se registró ningún rostro")