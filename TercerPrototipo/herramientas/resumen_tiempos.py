"""Resume los tiempos medidos por SmartGate durante el funcionamiento real.

Lee data/metricas/tiempos_pipeline.csv (un intento de acceso por fila) y
data/metricas/tiempos_deteccion.csv (una inferencia de YuNet por fila), que se
generan con `metricas.habilitadas: true` en config/config.yaml.

Uso, desde la carpeta TercerPrototipo:

    python3 herramientas/resumen_tiempos.py
    python3 herramientas/resumen_tiempos.py --markdown data/metricas/resumen.md
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from estadisticas import resumir, tabla_markdown, tabla_texto

RAIZ = Path(__file__).resolve().parents[1]

# (columna del CSV, nombre para la tabla), en el orden del pipeline.
ETAPAS = (
    ("preparacion_deteccion_ms", "Redimensionado para YuNet"),
    ("yunet_ms", "YuNet (detección)"),
    ("recorte_y_buffers_ms", "Recortes y carga de buffers"),
    ("traspaso_a_antispoof_ms", "Traspaso detección → antispoofing"),
    ("preparacion_antispoof_ms", "Preparación de la entrada 80x80"),
    ("minifasnet_ms", "MiniFASNetV2 (antispoofing)"),
    ("antispoof_total_ms", "Antispoofing completo"),
    ("traspaso_a_reconocimiento_ms", "Traspaso antispoofing → reconocimiento"),
    ("alineado_ms", "Alineado del rostro"),
    ("sface_ms", "SFace (embedding)"),
    ("comparacion_galeria_ms", "Comparación con la galería"),
    ("reconocimiento_total_ms", "Reconocimiento completo"),
    ("traspaso_a_gestor_ms", "Traspaso modelo → Pipeline Manager"),
    ("gestor_ms", "Decisión del Pipeline Manager"),
    ("senal_a_pulso_ms", "Orden → pulso de apertura (GPIO)"),
)

TOTALES = (
    ("total_hasta_decision_ms", "Cuadro capturado → decisión"),
    ("total_hasta_senal_ms", "Cuadro capturado → LED de resultado"),
    ("total_hasta_pulso_ms", "Cuadro capturado → pulso al portón"),
)


def leer_csv(ruta):
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8") as archivo:
        return list(csv.DictReader(archivo))


def valores(filas, columna):
    salida = []
    for fila in filas:
        texto = (fila.get(columna) or "").strip()
        if texto:
            salida.append(float(texto))
    return salida


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--carpeta", default=str(RAIZ / "data" / "metricas"))
    parser.add_argument("--markdown", help="guardar también el resumen en Markdown")
    args = parser.parse_args()

    carpeta = Path(args.carpeta)
    intentos = leer_csv(carpeta / "tiempos_pipeline.csv")
    cuadros = leer_csv(carpeta / "tiempos_deteccion.csv")

    if not intentos and not cuadros:
        print(f"No hay mediciones en {carpeta}.")
        print("Activá `metricas.habilitadas: true` en config/config.yaml y usá SmartGate.")
        return

    por_resultado = defaultdict(list)
    for fila in intentos:
        por_resultado[fila["resultado"]].append(fila)

    secciones = []

    conteo = ", ".join(f"{len(f)} {r}" for r, f in sorted(por_resultado.items()))
    secciones.append(("texto", f"Intentos registrados: {len(intentos)} ({conteo})"))

    etapas = [(nombre, resumir(valores(intentos, col))) for col, nombre in ETAPAS]
    secciones.append(("tabla", "Etapas y traspasos del pipeline (todos los intentos, ms)", etapas))

    for resultado, filas in sorted(por_resultado.items()):
        totales = [(nombre, resumir(valores(filas, col))) for col, nombre in TOTALES]
        if any(r for _n, r in totales):
            secciones.append(("tabla", f"Tiempo total — intentos «{resultado}» (ms)", totales))

    if cuadros:
        tiempos = valores(cuadros, "yunet_ms")
        activos = [float(f["yunet_ms"]) for f in cuadros if f.get("modo") == "activo"]
        con_rostro = [float(f["yunet_ms"]) for f in cuadros if f.get("rostro") == "1"]
        detector = [
            ("YuNet, todos los cuadros", resumir(tiempos)),
            ("YuNet, modo activo", resumir(activos)),
            ("YuNet, cuadros con rostro", resumir(con_rostro)),
        ]
        secciones.append(("tabla", "Inferencias de YuNet durante la búsqueda (ms)", detector))
        media = resumir(tiempos)["media"]
        secciones.append(("texto", f"Con ese tiempo, YuNet puede analizar hasta {1000 / media:.1f} cuadros por segundo."))

    autorizados = por_resultado.get("autorizado", [])
    pulso = resumir(valores(autorizados, "total_hasta_pulso_ms"))
    hasta = "el pulso de apertura del portón"
    if pulso is None:
        # Modo solo cámara: no hay pulso, el usuario ve el LED verde.
        pulso = resumir(valores(autorizados, "total_hasta_senal_ms"))
        hasta = "el LED verde (modo solo cámara)"
    if pulso:
        secciones.append((
            "texto",
            f"Un usuario autorizado espera en promedio {pulso['media'] / 1000:.2f} s "
            f"(P95: {pulso['p95'] / 1000:.2f} s) desde que la cámara entrega el cuadro "
            f"hasta {hasta}.",
        ))

    for seccion in secciones:
        print()
        print(seccion[1] if seccion[0] == "texto" else tabla_texto(seccion[2], seccion[1]))

    if args.markdown:
        lineas = ["# Tiempos medidos en SmartGate", ""]
        for seccion in secciones:
            if seccion[0] == "texto":
                lineas += [seccion[1], ""]
            else:
                lineas += [f"## {seccion[1]}", "", tabla_markdown(seccion[2]), ""]
        Path(args.markdown).write_text("\n".join(lineas), encoding="utf-8")
        print(f"\nResumen guardado en {args.markdown}")


if __name__ == "__main__":
    main()
