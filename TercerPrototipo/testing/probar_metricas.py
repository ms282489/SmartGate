"""Comprueba el registro de tiempos sin cámara ni modelos."""

import csv
import tempfile
from pathlib import Path

from core.metricas import MedidorTiempos


with tempfile.TemporaryDirectory() as carpeta:
    medidor = MedidorTiempos()

    # Con la medición apagada no se escribe nada.
    medidor.configurar({"metricas": {"habilitadas": False, "carpeta": carpeta}})
    medidor.nuevo_intento({"captura": 0.0})
    medidor.cerrar("autorizado")
    assert not (Path(carpeta) / "tiempos_pipeline.csv").exists()

    medidor.configurar({"metricas": {"habilitadas": True, "carpeta": carpeta}})

    # Intento autorizado con todos los hitos (segundos simulados).
    medidor.nuevo_intento({
        "captura": 10.000,
        "deteccion_inicio": 10.004,
        "deteccion_fin": 10.034,
        "muestras_listas": 10.040,
    })
    medidor.anotar(puntaje_deteccion=0.93)
    for hito, instante in (
        ("antispoof_inicio", 10.041),
        ("antispoof_inferencia_inicio", 10.043),
        ("antispoof_inferencia_fin", 10.058),
        ("antispoof_fin", 10.059),
        ("reconocimiento_inicio", 10.060),
        ("reconocimiento_alineado", 10.065),
        ("reconocimiento_embedding", 10.105),
        ("reconocimiento_fin", 10.106),
        ("gestor_resultado", 10.108),
        ("gestor_senal", 10.110),
        ("pulso_apertura", 10.112),
    ):
        medidor.marcar(hito, instante)
    # Una marca repetida no reemplaza a la primera.
    medidor.marcar("antispoof_inicio", 99.0)
    medidor.anotar(similitud=0.81, personas_en_galeria=3)
    medidor.cerrar("autorizado")

    # Intento rechazado por antispoofing: sin reconocimiento ni pulso.
    medidor.nuevo_intento({"captura": 20.0, "deteccion_inicio": 20.0,
                           "deteccion_fin": 20.03, "muestras_listas": 20.035})
    medidor.marcar("antispoof_inicio", 20.036)
    medidor.marcar("antispoof_fin", 20.05)
    medidor.marcar("gestor_resultado", 20.052)
    medidor.marcar("gestor_senal", 20.053)
    medidor.cerrar("spoof")

    # Un error descarta el intento.
    medidor.nuevo_intento({"captura": 30.0})
    medidor.descartar()
    medidor.cerrar("rechazado")

    for _ in range(3):
        medidor.registrar_deteccion(0.031, True, False)
    medidor.cerrar_archivos()

    with (Path(carpeta) / "tiempos_pipeline.csv").open(encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))

    assert [f["resultado"] for f in filas] == ["autorizado", "spoof"]
    autorizado, spoof = filas
    assert autorizado["yunet_ms"] == "30.00"
    assert autorizado["traspaso_a_antispoof_ms"] == "1.00"
    assert autorizado["sface_ms"] == "40.00"
    assert autorizado["traspaso_a_gestor_ms"] == "2.00"
    assert autorizado["total_hasta_pulso_ms"] == "112.00"
    assert autorizado["similitud"] == "0.8100"
    assert autorizado["personas_en_galeria"] == "3"
    assert spoof["sface_ms"] == ""
    assert spoof["total_hasta_pulso_ms"] == ""
    assert spoof["traspaso_a_gestor_ms"] == "2.00"

    with (Path(carpeta) / "tiempos_deteccion.csv").open(encoding="utf-8") as archivo:
        cuadros = list(csv.DictReader(archivo))
    assert len(cuadros) == 3 and cuadros[0]["yunet_ms"] == "31.00"

print("Registro de tiempos del pipeline: correcto")
