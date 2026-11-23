"""Worker encargado del reconocimiento facial."""

from pathlib import Path

import cv2

from core.buffers import tomar_buffer2
from core.metricas import medidor
from core.states import MensajePipeline, ResultadoPipeline
from Tareas.reconocimiento.galeria import (
    galeria_compartida,
)


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]

RUTA_MODELO = (
    CARPETA_PROYECTO
    / "app"
    / "Tareas"
    / "reconocimiento"
    / "face_recognition_sface_2021dec.onnx"
)

def reconocimiento_worker(
    config,
    sincronizacion,
    cola_mensajes,
    vista_camara=None,
):
    """Compara el rostro con las personas autorizadas."""
    umbral_reconocimiento = (
        config["thresholds"]["recognition"]
    )
    try:
        reconocedor = cv2.FaceRecognizerSF.create(
            str(RUTA_MODELO),
            "",
        )

    except Exception as error:
        print(
            "No se pudo iniciar el reconocimiento:",
            error,
        )
        cola_mensajes.put(MensajePipeline.APAGAR)
        return

    while not sincronizacion.shutdown.is_set():
        rostro_disponible = (
            sincronizacion.recognition_ready.wait(
                timeout=1
            )
        )

        if sincronizacion.shutdown.is_set():
            break

        if not rostro_disponible:
            continue

        sincronizacion.model3_idle.clear()

        try:
            imagen, rostro_detectado = tomar_buffer2()
            medidor.marcar("reconocimiento_inicio")
            sincronizacion.recognition_ready.clear()

            rostro_alineado = reconocedor.alignCrop(
                imagen,
                rostro_detectado,
            )
            medidor.marcar("reconocimiento_alineado")
            embedding_actual = reconocedor.feature(
                rostro_alineado
            )
            medidor.marcar("reconocimiento_embedding")
            personas_autorizadas = galeria_compartida.obtener()

            mejor_persona = None
            mejor_similitud = None

            for persona in personas_autorizadas:
                similitud = reconocedor.match(
                    embedding_actual,
                    persona["embedding"],
                    cv2.FaceRecognizerSF_FR_COSINE,
                )

                if (
                    mejor_similitud is None
                    or similitud > mejor_similitud
                ):
                    mejor_similitud = similitud
                    mejor_persona = persona

            medidor.marcar("reconocimiento_fin")
            medidor.anotar(
                similitud=(
                    float(mejor_similitud)
                    if mejor_similitud is not None
                    else None
                ),
                personas_en_galeria=len(personas_autorizadas),
            )

            if (
                mejor_persona is not None
                and mejor_similitud is not None
                and mejor_similitud
                >= umbral_reconocimiento
            ):
                print(
                    "Identidad autorizada:",
                    mejor_persona["name"],
                    "- similitud:",
                    f"{mejor_similitud * 100:.1f}%",
                )
                if vista_camara is not None:
                    vista_camara.actualizar_reconocimiento(
                        mejor_persona["name"],
                        mejor_similitud,
                        True,
                    )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_AUTORIZADA
                        ),
                        persona_id=mejor_persona["id"],
                        similitud=float(mejor_similitud),
                        antispoof=(
                            sincronizacion.antispoof_score
                        ),
                        deteccion=(
                            sincronizacion.detection_score
                        ),
                    )
                )
            else:
                if mejor_similitud is None:
                    print(
                        "Identidad rechazada: "
                        "no hay embeddings activos"
                    )
                else:
                    print(
                        "Identidad rechazada - similitud:",
                        f"{mejor_similitud * 100:.1f}%",
                    )
                if vista_camara is not None:
                    vista_camara.actualizar_reconocimiento(
                        None,
                        mejor_similitud,
                        False,
                    )
                cola_mensajes.put(
                    ResultadoPipeline(
                        mensaje=(
                            MensajePipeline.IDENTIDAD_RECHAZADA
                        ),
                        similitud=(
                            float(mejor_similitud)
                            if mejor_similitud is not None
                            else None
                        ),
                        antispoof=(
                            sincronizacion.antispoof_score
                        ),
                        deteccion=(
                            sincronizacion.detection_score
                        ),
                    )
                )

        except Exception as error:
            sincronizacion.recognition_ready.clear()
            print(
                "Error durante el reconocimiento:",
                error,
            )
            cola_mensajes.put(MensajePipeline.ERROR)

        finally:
            sincronizacion.model3_idle.set()
