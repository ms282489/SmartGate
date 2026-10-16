"""Comprueba la sintaxis de todos los archivos Python."""

import ast
from pathlib import Path


raiz = Path(__file__).resolve().parents[1]

archivos_python = list(
    (raiz / "app").rglob("*.py")
)

archivos_python.extend(
    (raiz / "tests").rglob("*.py")
)

archivos_python.append(
    raiz / "data/registrar_rostros.py"
)

for archivo in archivos_python:
    contenido = archivo.read_text(encoding="utf-8")
    ast.parse(contenido, filename=str(archivo))

print(
    "Sintaxis correcta en",
    len(archivos_python),
    "archivos Python",
)
