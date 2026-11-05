"""Galería facial compartida y respaldo persistente para modo offline."""

import os
import tempfile
from pathlib import Path
from threading import Lock

import numpy as np


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_GALERIA_LOCAL = CARPETA_PROYECTO / "data" / "galeria_rostros.npz"
RUTA_EMBEDDINGS_LEGACY = CARPETA_PROYECTO / "data" / "embeddings.npy"


def _normalizar_personas(personas):
    """Valida la forma de la galería y evita compartir datos mutables."""

    normalizadas = []

    for persona in personas:
        embedding = np.asarray(
            persona["embedding"],
            dtype=np.float32,
        ).reshape(1, -1)

        if embedding.size != 128 or not np.isfinite(embedding).all():
            raise ValueError("La galería contiene un embedding inválido")

        normalizadas.append(
            {
                "id": persona.get("id"),
                "name": str(persona.get("name") or "Usuario sin nombre"),
                "embedding": embedding.copy(),
            }
        )

    return normalizadas


class GaleriaCompartida:
    """Permite reemplazar la galería sin interrumpir reconocimientos."""

    def __init__(self):
        self._lock = Lock()
        self._personas = ()

    def reemplazar(self, personas):
        normalizadas = tuple(_normalizar_personas(personas))
        with self._lock:
            self._personas = normalizadas

    def obtener(self):
        with self._lock:
            return list(self._personas)

    def cantidad(self):
        with self._lock:
            return len(self._personas)


galeria_compartida = GaleriaCompartida()


def galerias_equivalentes(primera, segunda):
    """Evita reescribir la tarjeta SD cuando no hubo cambios."""

    if len(primera) != len(segunda):
        return False

    for persona_a, persona_b in zip(primera, segunda):
        if persona_a.get("id") != persona_b.get("id"):
            return False
        if persona_a.get("name") != persona_b.get("name"):
            return False
        if not np.array_equal(
            np.asarray(persona_a["embedding"]),
            np.asarray(persona_b["embedding"]),
        ):
            return False

    return True


def guardar_respaldo_local(personas, ruta=None):
    """Guarda IDs, nombres y embeddings mediante reemplazo atómico."""

    ruta = Path(ruta or RUTA_GALERIA_LOCAL)
    normalizadas = _normalizar_personas(personas)
    ids = np.asarray(
        [str(persona["id"] or "") for persona in normalizadas],
        dtype=str,
    )
    nombres = np.asarray(
        [persona["name"] for persona in normalizadas],
        dtype=str,
    )
    embeddings = (
        np.vstack([persona["embedding"] for persona in normalizadas])
        if normalizadas
        else np.empty((0, 128), dtype=np.float32)
    ).astype(np.float32)

    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, nombre_temporal = tempfile.mkstemp(
        prefix=ruta.name + ".",
        suffix=".tmp",
        dir=ruta.parent,
    )

    try:
        with os.fdopen(descriptor, "wb") as archivo:
            np.savez_compressed(
                archivo,
                ids=ids,
                nombres=nombres,
                embeddings=embeddings,
            )
            archivo.flush()
            os.fsync(archivo.fileno())

        os.replace(nombre_temporal, ruta)
    except Exception:
        try:
            os.unlink(nombre_temporal)
        except FileNotFoundError:
            pass
        raise


def _cargar_npz(ruta):
    with np.load(ruta, allow_pickle=False) as datos:
        ids = datos["ids"]
        nombres = datos["nombres"]
        embeddings = datos["embeddings"].astype(np.float32)

    if embeddings.ndim != 2 or embeddings.shape[1:] != (128,):
        raise ValueError("El respaldo local tiene dimensiones inválidas")
    if len(ids) != len(nombres) or len(ids) != len(embeddings):
        raise ValueError("El respaldo local está incompleto")
    if not np.isfinite(embeddings).all():
        raise ValueError("El respaldo local contiene valores inválidos")

    return [
        {
            "id": str(persona_id) or None,
            "name": str(nombre),
            "embedding": embedding.reshape(1, -1),
        }
        for persona_id, nombre, embedding in zip(
            ids,
            nombres,
            embeddings,
        )
    ]


def _cargar_respaldo_legacy(ruta):
    embeddings = np.load(ruta, allow_pickle=False).astype(np.float32)
    if embeddings.ndim != 2 or embeddings.shape[1:] != (128,):
        raise ValueError("embeddings.npy tiene dimensiones inválidas")

    return [
        {
            "id": None,
            "name": f"Usuario local {indice + 1}",
            "embedding": embedding.reshape(1, -1),
        }
        for indice, embedding in enumerate(embeddings)
    ]


def cargar_respaldo_local(ruta=None, ruta_legacy=None):
    """Carga la última galería válida sin requerir Internet."""

    ruta = Path(ruta or RUTA_GALERIA_LOCAL)
    ruta_legacy = Path(ruta_legacy or RUTA_EMBEDDINGS_LEGACY)

    try:
        if ruta.exists():
            return _cargar_npz(ruta)
        if ruta_legacy.exists():
            return _cargar_respaldo_legacy(ruta_legacy)
    except Exception as error:
        print("No se pudo cargar el respaldo facial local:", error)

    return []
