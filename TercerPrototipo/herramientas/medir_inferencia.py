"""Benchmark de los tres modelos de SmartGate sobre la Raspberry Pi.

Ejecuta muchas veces la misma cadena que el pipeline (redimensionado, YuNet,
MiniFASNetV2, SFace y comparación con la galería) de forma secuencial, sin
hilos, sin GPIO y sin Supabase. Sirve para conocer el costo puro de cada
modelo en el hardware y justificar la elección de la placa.

Uso, desde la carpeta TercerPrototipo:

    # Con la cámara (una persona debe estar frente a ella):
    python3 herramientas/medir_inferencia.py --fuente camara

    # Con una fotografía que contenga un rostro (no necesita cámara):
    python3 herramientas/medir_inferencia.py --fuente imagen --imagen foto.jpg

Opciones útiles: --repeticiones 200, --personas 100 (galería simulada),
--deteccion-completa (mide también YuNet a la resolución completa).

Los resultados se muestran en la terminal y se guardan en data/metricas/ como
Markdown (para el informe) y JSON.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "app"))

from estadisticas import resumir, tabla_markdown, tabla_texto  # noqa: E402
from Tareas.antispoof.antispoof_worker import RUTA_MODELO as MODELO_ANTISPOOF  # noqa: E402
from Tareas.deteccion.deteccion_worker import (  # noqa: E402
    ESCALA_ANTISPOOF,
    RUTA_MODELO as MODELO_DETECCION,
    escalar_deteccion,
)
from Tareas.reconocimiento.reconocimiento_worker import (  # noqa: E402
    RUTA_MODELO as MODELO_RECONOCIMIENTO,
)


def leer(ruta):
    try:
        return Path(ruta).read_text().strip("\x00\n ")
    except OSError:
        return None


def temperatura_cpu():
    valor = leer("/sys/class/thermal/thermal_zone0/temp")
    return round(int(valor) / 1000, 1) if valor and valor.isdigit() else None


def info_sistema():
    """Datos de la placa para dejar documentada la medición."""

    info = {
        "placa": leer("/proc/device-tree/model") or platform.machine(),
        "sistema": platform.platform(),
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "nucleos": os.cpu_count(),
        "hilos_opencv": cv2.getNumThreads(),
    }
    memoria = leer("/proc/meminfo")
    if memoria:
        kb = int(memoria.split("\n")[0].split()[1])
        info["ram_gb"] = round(kb / 1024 / 1024, 1)
    frecuencia = leer("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
    if frecuencia and frecuencia.isdigit():
        info["frecuencia_max_mhz"] = int(frecuencia) // 1000
    gobernador = leer("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if gobernador:
        info["gobernador_cpu"] = gobernador
    return info


def estado_throttling():
    """Lee vcgencmd get_throttled si existe (0x0 = sin limitaciones)."""

    if not shutil.which("vcgencmd"):
        return None
    try:
        salida = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        return salida.split("=")[-1]
    except Exception:
        return None


def cargar_galeria(cantidad):
    """Usa la galería local real; si se pide más gente, completa con datos simulados."""

    personas = []
    try:
        from Tareas.reconocimiento.galeria import cargar_respaldo_local
        personas = [p["embedding"] for p in cargar_respaldo_local()]
    except Exception:
        personas = []

    real = len(personas)
    objetivo = max(cantidad or 0, real, 1)
    generador = np.random.default_rng(0)
    while len(personas) < objetivo:
        v = generador.standard_normal((1, 128)).astype(np.float32)
        personas.append(v / np.linalg.norm(v))
    return personas, real


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fuente", choices=("camara", "imagen"), default="camara")
    parser.add_argument("--imagen", help="fotografía con un rostro (si --fuente imagen)")
    parser.add_argument("--repeticiones", type=int, default=100)
    parser.add_argument("--calentamiento", type=int, default=10,
                        help="iteraciones iniciales que no se cuentan")
    parser.add_argument("--personas", type=int, default=0,
                        help="tamaño de galería a simular (0 = la galería local real)")
    parser.add_argument("--hilos", type=int, default=None,
                        help="hilos de OpenCV (por defecto, los de la placa)")
    parser.add_argument("--deteccion-completa", action="store_true",
                        help="medir también YuNet sobre la imagen completa")
    parser.add_argument("--salida", default=str(RAIZ / "data" / "metricas"))
    args = parser.parse_args()

    if args.hilos is not None:
        cv2.setNumThreads(args.hilos)

    config = yaml.safe_load((RAIZ / "config" / "config.yaml").read_text(encoding="utf-8"))
    cam_cfg = config["camera"]
    det_cfg = config.get("detection", {})
    umbral_det = config["thresholds"]["detection"]
    ancho_inf = int(det_cfg.get("inference_width", 640))
    alto_inf = int(det_cfg.get("inference_height", 480))

    # ---------------------------------------------------------- fuente
    camara = None
    if args.fuente == "camara":
        from core.camara import crear_camara
        camara = crear_camara(cam_cfg)
        ok, imagen = camara.read()
        if not ok:
            sys.exit("No se pudo leer la cámara")
    else:
        if not args.imagen:
            sys.exit("Indicá la fotografía con --imagen")
        imagen = cv2.imread(args.imagen)
        if imagen is None:
            sys.exit(f"No se pudo abrir {args.imagen}")
        # Igualar la resolución que entrega la cámara en el sistema real.
        imagen = cv2.resize(imagen, (int(cam_cfg["width"]), int(cam_cfg["height"])))
    alto, ancho = imagen.shape[:2]

    # ---------------------------------------------------------- modelos
    t = time.perf_counter()
    detector = cv2.FaceDetectorYN.create(
        str(MODELO_DETECCION), "", (ancho_inf, alto_inf), umbral_det, 0.3, 5000)
    carga_yunet = time.perf_counter() - t
    t = time.perf_counter()
    antispoof = cv2.dnn.readNetFromONNX(str(MODELO_ANTISPOOF))
    carga_minifas = time.perf_counter() - t
    t = time.perf_counter()
    reconocedor = cv2.FaceRecognizerSF.create(str(MODELO_RECONOCIMIENTO), "")
    carga_sface = time.perf_counter() - t
    detector_completo = None
    if args.deteccion_completa:
        detector_completo = cv2.FaceDetectorYN.create(
            str(MODELO_DETECCION), "", (ancho, alto), umbral_det, 0.3, 5000)

    galeria, personas_reales = cargar_galeria(args.personas)

    etapas = {k: [] for k in (
        "captura", "redimensionado", "yunet", "recorte_antispoof",
        "minifasnet", "alineado", "sface", "comparacion", "total")}
    if detector_completo is not None:
        etapas["yunet_completa"] = []
    sin_rostro = 0
    temp_inicio = temperatura_cpu()
    total_iter = args.calentamiento + args.repeticiones
    print(f"Midiendo {args.repeticiones} repeticiones (+{args.calentamiento} de calentamiento)...")

    i = 0
    intentos = 0
    while i < total_iter:
        intentos += 1
        if intentos > total_iter * 20:
            sys.exit("Demasiados cuadros sin rostro: ubicate frente a la cámara o usá otra imagen")
        medicion = {}
        t0 = time.perf_counter()
        if camara is not None:
            ok, cuadro = camara.read()
            if not ok:
                continue
        else:
            cuadro = imagen
        t1 = time.perf_counter()
        medicion["captura"] = t1 - t0

        cuadro_det = cv2.resize(cuadro, (ancho_inf, alto_inf), interpolation=cv2.INTER_AREA)
        t2 = time.perf_counter()
        medicion["redimensionado"] = t2 - t1
        detector.setInputSize((ancho_inf, alto_inf))
        _, rostros = detector.detect(cuadro_det)
        t3 = time.perf_counter()
        medicion["yunet"] = t3 - t2
        if rostros is None or len(rostros) == 0:
            sin_rostro += 1
            continue

        rostro = escalar_deteccion(rostros[0], ancho / ancho_inf, alto / alto_inf)
        # Mismo recorte ampliado que el worker de detección.
        x, y, w, h = (int(v) for v in rostro[:4])
        cx, cy = x + w / 2, y + h / 2
        rw, rh = w * ESCALA_ANTISPOOF, h * ESCALA_ANTISPOOF
        recorte = cuadro[max(0, int(cy - rh / 2)):min(alto, int(cy + rh / 2)),
                         max(0, int(cx - rw / 2)):min(ancho, int(cx + rw / 2))].copy()
        recorte = cv2.resize(recorte, (80, 80))
        entrada = cv2.dnn.blobFromImage(recorte, 1.0, (80, 80), swapRB=False, crop=False)
        t4 = time.perf_counter()
        medicion["recorte_antispoof"] = t4 - t3
        antispoof.setInput(entrada)
        salida = antispoof.forward()[0]
        valores = np.exp(salida - np.max(salida))
        _ = valores / np.sum(valores)
        t5 = time.perf_counter()
        medicion["minifasnet"] = t5 - t4

        alineado = reconocedor.alignCrop(cuadro, rostro)
        t6 = time.perf_counter()
        medicion["alineado"] = t6 - t5
        embedding = reconocedor.feature(alineado)
        t7 = time.perf_counter()
        medicion["sface"] = t7 - t6
        mejor = max(
            reconocedor.match(embedding, e, cv2.FaceRecognizerSF_FR_COSINE)
            for e in galeria
        )
        t8 = time.perf_counter()
        medicion["comparacion"] = t8 - t7
        medicion["total"] = t8 - t0

        if detector_completo is not None:
            t9 = time.perf_counter()
            detector_completo.detect(cuadro)
            medicion["yunet_completa"] = time.perf_counter() - t9

        if i >= args.calentamiento:
            for clave, valor in medicion.items():
                etapas[clave].append(valor * 1000)
        i += 1

    temp_fin = temperatura_cpu()
    if camara is not None:
        camara.release()

    nombres = [
        ("Captura de cámara", "captura"),
        (f"Redimensionado a {ancho_inf}x{alto_inf}", "redimensionado"),
        (f"YuNet ({ancho_inf}x{alto_inf})", "yunet"),
        ("Recorte y entrada antispoofing", "recorte_antispoof"),
        ("MiniFASNetV2", "minifasnet"),
        ("Alineado del rostro", "alineado"),
        ("SFace (embedding)", "sface"),
        (f"Comparación con {len(galeria)} personas", "comparacion"),
        ("Total secuencial por intento", "total"),
    ]
    if detector_completo is not None:
        nombres.insert(3, (f"YuNet ({ancho}x{alto}, referencia)", "yunet_completa"))
    if camara is None:
        nombres = [n for n in nombres if n[1] != "captura"]

    resumenes = [(nombre, resumir(etapas[clave])) for nombre, clave in nombres]
    yunet = resumir(etapas["yunet"])
    total = resumir(etapas["total"])

    info = info_sistema()
    info.update({
        "fuente": args.fuente,
        "resolucion_camara": f"{ancho}x{alto}",
        "personas_galeria": len(galeria),
        "personas_reales": personas_reales,
        "temperatura_inicio_c": temp_inicio,
        "temperatura_fin_c": temp_fin,
        "throttling": estado_throttling(),
        "cuadros_sin_rostro": sin_rostro,
        "carga_modelos_ms": {
            "yunet": round(carga_yunet * 1000, 1),
            "minifasnet": round(carga_minifas * 1000, 1),
            "sface": round(carga_sface * 1000, 1),
        },
    })

    texto = tabla_texto(resumenes, "Tiempos por etapa (ms)")
    print()
    print(texto)
    print()
    print(f"YuNet puede analizar hasta {1000 / yunet['media']:.1f} cuadros por segundo.")
    print(f"Un intento completo (detección + antispoofing + reconocimiento) "
          f"toma en promedio {total['media']:.0f} ms (P95: {total['p95']:.0f} ms).")
    print()
    for clave, valor in info.items():
        print(f"  {clave}: {valor}")

    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_md = carpeta / f"benchmark_{sello}.md"
    ruta_json = carpeta / f"benchmark_{sello}.json"

    lineas = [
        f"# Benchmark de inferencia SmartGate ({datetime.now():%Y-%m-%d %H:%M})",
        "",
        f"- Placa: {info['placa']}",
        f"- OpenCV {info['opencv']}, {info['nucleos']} núcleos, {info['hilos_opencv']} hilos",
        f"- Fuente: {args.fuente}, resolución {ancho}x{alto}, "
        f"{args.repeticiones} repeticiones (+{args.calentamiento} de calentamiento)",
        f"- Galería: {len(galeria)} personas ({personas_reales} reales)",
        f"- Temperatura CPU: {temp_inicio} °C → {temp_fin} °C, throttling: {info['throttling']}",
        "",
        tabla_markdown(resumenes),
        "",
        f"YuNet admite hasta **{1000 / yunet['media']:.1f} cuadros/s**. "
        f"Un intento completo toma **{total['media']:.0f} ms** en promedio "
        f"(P95: {total['p95']:.0f} ms).",
        "",
    ]
    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    ruta_json.write_text(json.dumps({
        "sistema": info,
        "repeticiones": args.repeticiones,
        "etapas_ms": {clave: resumir(valores) for clave, valores in etapas.items() if valores},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados guardados en:\n  {ruta_md}\n  {ruta_json}")


if __name__ == "__main__":
    main()
