"""Sincroniza las fotografías de Supabase Storage con los embeddings."""

from pathlib import Path

import cv2
import numpy as np


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]

RUTA_DETECTOR = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "deteccion"
    / "face_detection_yunet_2023mar.onnx"
)

BUCKET_ROSTROS = "face-images"
EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".webp")

# Las fotografías de registro suelen tener más fondo y el rostro ocupa
# menos espacio que durante el uso de la cámara. Un umbral independiente
# evita rechazar fotos válidas sin relajar la detección del pipeline.
UMBRAL_DETECCION_REGISTRO = 0.65


def _listar_imagenes(bucket, persona_id):
    """Devuelve las rutas de las imágenes de una persona."""

    objetos = bucket.list(
        persona_id,
        {
            "limit": 100,
            "sortBy": {
                "column": "created_at",
                "order": "asc",
            },
        },
    )

    return [
        f"{persona_id}/{objeto['name']}"
        for objeto in objetos
        if objeto.get("name", "").lower().endswith(
            EXTENSIONES_VALIDAS
        )
    ]


def _generar_embedding(
    contenido,
    detector,
    reconocedor,
):
    """Genera un embedding SFace desde los bytes de una imagen."""

    datos = np.frombuffer(
        contenido,
        dtype=np.uint8,
    )
    imagen = cv2.imdecode(
        datos,
        cv2.IMREAD_COLOR,
    )

    if imagen is None:
        raise ValueError("La imagen no se pudo decodificar")

    detector.setInputSize(
        (imagen.shape[1], imagen.shape[0])
    )
    _, rostros = detector.detect(imagen)

    if rostros is None or len(rostros) != 1:
        raise ValueError(
            "La imagen debe contener exactamente un rostro"
        )

    rostro_alineado = reconocedor.alignCrop(
        imagen,
        rostros[0],
    )
    embedding = reconocedor.feature(
        rostro_alineado
    )[0]

    if embedding.size != 128:
        raise ValueError(
            "El modelo no produjo un embedding de 128 valores"
        )

    return embedding.astype(np.float32).tolist()


def sincronizar_rostros_supabase(
    cliente,
    config,
    reconocedor,
):
    """Crea y elimina embeddings según las fotos del panel web."""

    detector = cv2.FaceDetectorYN.create(
        str(RUTA_DETECTOR),
        "",
        (320, 320),
        min(
            config["thresholds"]["detection"],
            UMBRAL_DETECCION_REGISTRO,
        ),
        0.3,
        5000,
    )

    personas = (
        cliente.table("people")
        .select("id,name")
        .execute()
        .data
    )
    filas = (
        cliente.table("face_embeddings")
        .select("id,person_id,source_path")
        .not_.is_("source_path", "null")
        .execute()
        .data
    )

    filas_por_ruta = {
        fila["source_path"]: fila
        for fila in filas
        if fila.get("source_path")
    }
    rutas_storage = set()
    bucket = cliente.storage.from_(BUCKET_ROSTROS)
    creados = 0
    eliminados = 0

    for persona in personas:
        persona_id = persona["id"]
        rutas = _listar_imagenes(
            bucket,
            persona_id,
        )
        rutas_storage.update(rutas)

        for ruta in rutas:
            if ruta in filas_por_ruta:
                continue

            try:
                contenido = bucket.download(ruta)
                embedding = _generar_embedding(
                    contenido,
                    detector,
                    reconocedor,
                )
                (
                    cliente.table("face_embeddings")
                    .insert(
                        {
                            "person_id": persona_id,
                            "embedding": embedding,
                            "source_path": ruta,
                        }
                    )
                    .execute()
                )
                creados += 1
                print(
                    "Embedding creado desde:",
                    ruta,
                )

            except Exception as error:
                print(
                    "No se pudo procesar la foto",
                    ruta,
                    ":",
                    error,
                )

    for ruta, fila in filas_por_ruta.items():
        if ruta in rutas_storage:
            continue

        (
            cliente.table("face_embeddings")
            .delete()
            .eq("id", fila["id"])
            .execute()
        )
        eliminados += 1

    print(
        "Sincronización facial finalizada:",
        creados,
        "creados,",
        eliminados,
        "eliminados",
    )

