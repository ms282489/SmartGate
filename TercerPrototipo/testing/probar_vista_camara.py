"""Prueba los resultados superpuestos sin abrir una ventana gráfica."""

import numpy as np

from core.vista_camara import VistaCamaraCompartida


vista = VistaCamaraCompartida()
imagen = np.zeros((480, 640, 3), dtype=np.uint8)

vista.actualizar(imagen)
vista.actualizar_supabase(False, 3)
vista.actualizar_deteccion(
    np.asarray([100, 80, 120, 140, 0.97], dtype=np.float32),
    0.97,
)
vista.actualizar_antispoof(0.88, True)
vista.actualizar_reconocimiento("Persona Prueba", 0.91, True)
vista.actualizar_estado("RESULTADO: AUTORIZADO 91.0%", (0, 255, 0))

version, imagen_publicada, datos = vista.obtener_si_cambio(-1)

assert version >= 0
assert imagen_publicada is imagen
assert datos["rostro"] == (100, 80, 120, 140)
assert [texto for texto, _color in datos["estados"]] == [
    "SUPABASE: SIN CONEXION - CACHE: 3 EMBEDDINGS",
    "DETECCION: APROBADA 0.97",
    "ANTISPOOF: APROBADO 0.88",
    "RECONOCIMIENTO: Persona Prueba 91.0%",
    "RESULTADO: AUTORIZADO 91.0%",
]

version_sin_cambios, imagen_sin_cambios, datos_sin_cambios = (
    vista.obtener_si_cambio(version)
)
assert version_sin_cambios == version
assert imagen_sin_cambios is None
assert datos_sin_cambios is None

vista.preparar_busqueda()
_version, _imagen, datos = vista.obtener_si_cambio(version)
textos = [texto for texto, _color in datos["estados"]]

assert datos["rostro"] is None
assert textos[0] == "SUPABASE: SIN CONEXION - CACHE: 3 EMBEDDINGS"
assert textos[1:] == [
    "DETECCION: SIN ROSTRO",
    "ANTISPOOF: NO EVALUADO",
    "RECONOCIMIENTO: NO EVALUADO",
    "RESULTADO: ESPERANDO",
]

print("Prueba de vista completa de cámara: correcta")
