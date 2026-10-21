"""Prueba los tres modelos utilizando la cámara de la Mac."""

import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from Tareas.reconocimiento.reconocimiento_worker import (
    cargar_personas_supabase,
    crear_cliente_supabase,
)


raiz = Path(__file__).resolve().parents[1]

with open(
    raiz / "config/config.yaml",
    "r",
    encoding="utf-8",
) as archivo:
    config = yaml.safe_load(archivo)

camera_config = config["camera"]
umbrales = config["thresholds"]

ancho = camera_config["width"]
alto = camera_config["height"]
indice_camara = camera_config["index"]

# Durante esta prueba el panel web puede seguir modificando personas
# y fotografías. Las activaciones se consultan con frecuencia y las
# fotos se procesan cada pocos segundos.
INTERVALO_ACTUALIZACION_ACCESOS = 2
INTERVALO_SINCRONIZACION_FOTOS = 10

detector = cv2.FaceDetectorYN.create(
    str(
        raiz
        / "app/Tareas/deteccion/face_detection_yunet_2023mar.onnx"
    ),
    "",
    (ancho, alto),
    umbrales["detection"],
    0.3,
    5000,
)

modelo_antispoof = cv2.dnn.readNetFromONNX(
    str(
        raiz
        / "app/Tareas/antispoof/MiniFASNetV2.onnx"
    )
)

reconocedor = cv2.FaceRecognizerSF.create(
    str(
        raiz
        / "app/Tareas/reconocimiento/face_recognition_sface_2021dec.onnx"
    ),
    "",
)


def cargar_galeria(
    cliente=None,
    sincronizar_fotos=True,
):
    """Carga desde Supabase los embeddings de personas activas."""

    if cliente is None:
        cliente = crear_cliente_supabase()

    personas = cargar_personas_supabase(
        config,
        reconocedor,
        cliente=cliente,
        sincronizar_fotos=sincronizar_fotos,
    )

    return cliente, personas


try:
    cliente_supabase, personas_autorizadas = cargar_galeria(
        sincronizar_fotos=True,
    )

    print(
        "Embeddings activos cargados desde Supabase:",
        len(personas_autorizadas),
    )

except Exception as error:
    raise RuntimeError(
        "No se pudieron cargar los embeddings activos desde "
        f"Supabase: {error}"
    ) from error

estado_supabase = (
    "SUPABASE: "
    f"{len(personas_autorizadas)} EMBEDDINGS ACTIVOS"
)
color_supabase = (0, 255, 0)

ahora = time.monotonic()
ultima_actualizacion_accesos = ahora
ultima_sincronizacion_fotos = ahora

camara = cv2.VideoCapture(indice_camara)
camara.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
camara.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)

if not camara.isOpened():
    raise RuntimeError(
        "No se pudo abrir la cámara. Revisá los permisos de macOS."
    )

print("Cámara iniciada. Presioná Q para terminar.")

try:
    while True:
        lectura_correcta, imagen = camara.read()

        if not lectura_correcta:
            raise RuntimeError(
                "No se pudo obtener una imagen de la cámara"
            )

        ahora = time.monotonic()
        debe_actualizar_accesos = (
            ahora - ultima_actualizacion_accesos
            >= INTERVALO_ACTUALIZACION_ACCESOS
        )
        debe_sincronizar_fotos = (
            ahora - ultima_sincronizacion_fotos
            >= INTERVALO_SINCRONIZACION_FOTOS
        )

        if debe_actualizar_accesos or debe_sincronizar_fotos:
            ultima_actualizacion_accesos = ahora

            if debe_sincronizar_fotos:
                ultima_sincronizacion_fotos = ahora

            try:
                cantidad_anterior = len(personas_autorizadas)

                (
                    cliente_supabase,
                    personas_actualizadas,
                ) = cargar_galeria(
                    cliente=cliente_supabase,
                    sincronizar_fotos=(
                        debe_sincronizar_fotos
                    ),
                )

                personas_autorizadas = personas_actualizadas
                cantidad_actual = len(personas_autorizadas)

                estado_supabase = (
                    "SUPABASE: "
                    f"{cantidad_actual} EMBEDDINGS ACTIVOS"
                )
                color_supabase = (0, 255, 0)

                if cantidad_actual != cantidad_anterior:
                    print(
                        "Galería actualizada desde Supabase:",
                        cantidad_actual,
                        "embeddings activos",
                    )

            except Exception as error:
                # Mantener la última galería válida y volver a crear
                # la conexión en el siguiente intento.
                cliente_supabase = None
                estado_supabase = "SUPABASE: ERROR DE SINCRONIZACION"
                color_supabase = (0, 0, 255)
                print(
                    "No se pudo actualizar Supabase:",
                    error,
                )

        detector.setInputSize(
            (imagen.shape[1], imagen.shape[0])
        )

        resultado, rostros = detector.detect(imagen)

        estado_deteccion = "DETECCION: SIN ROSTRO"
        estado_antispoof = "ANTISPOOF: NO EVALUADO"
        estado_reconocimiento = "RECONOCIMIENTO: NO EVALUADO"
        resultado_final = "RESULTADO: ESPERANDO"

        color_deteccion = (255, 255, 255)
        color_antispoof = (180, 180, 180)
        color_reconocimiento = (180, 180, 180)
        color_resultado = (0, 255, 255)

        if rostros is not None:
            rostro_detectado = rostros[0]

            puntaje_deteccion = float(
                rostro_detectado[-1]
            )

            estado_deteccion = (
                f"DETECCION: APROBADA {puntaje_deteccion:.2f}"
            )
            color_deteccion = (0, 255, 0)

            x = int(rostro_detectado[0])
            y = int(rostro_detectado[1])
            ancho_rostro = int(rostro_detectado[2])
            alto_rostro = int(rostro_detectado[3])

            centro_x = x + ancho_rostro / 2
            centro_y = y + alto_rostro / 2

            ancho_recorte = ancho_rostro * 2.7
            alto_recorte = alto_rostro * 2.7

            inicio_x = max(
                0,
                int(centro_x - ancho_recorte / 2),
            )
            inicio_y = max(
                0,
                int(centro_y - alto_recorte / 2),
            )
            fin_x = min(
                imagen.shape[1],
                int(centro_x + ancho_recorte / 2),
            )
            fin_y = min(
                imagen.shape[0],
                int(centro_y + alto_recorte / 2),
            )

            rostro = imagen[
                inicio_y:fin_y,
                inicio_x:fin_x,
            ].copy()

            if rostro.size == 0:
                resultado_final = "RESULTADO: RECORTE INVALIDO"
                color_resultado = (0, 0, 255)

            else:
                rostro_antispoof = cv2.resize(
                    rostro,
                    (80, 80),
                )

                entrada = cv2.dnn.blobFromImage(
                    rostro_antispoof,
                    scalefactor=1.0,
                    size=(80, 80),
                    swapRB=False,
                    crop=False,
                )

                modelo_antispoof.setInput(entrada)
                salida = modelo_antispoof.forward()[0]

                valores = np.exp(
                    salida - np.max(salida)
                )
                probabilidades = valores / np.sum(valores)
                puntaje_real = float(probabilidades[1])

                if puntaje_real < umbrales["antispoof"]:
                    estado_antispoof = (
                        f"ANTISPOOF: RECHAZADO {puntaje_real:.2f}"
                    )
                    color_antispoof = (0, 0, 255)
                    resultado_final = "RESULTADO: SPOOF"
                    color_resultado = (0, 0, 255)

                else:
                    estado_antispoof = (
                        f"ANTISPOOF: APROBADO {puntaje_real:.2f}"
                    )
                    color_antispoof = (0, 255, 0)

                    rostro_alineado = reconocedor.alignCrop(
                        imagen,
                        rostro_detectado,
                    )

                    embedding_actual = reconocedor.feature(
                        rostro_alineado
                    )

                    mejor_similitud = None
                    mejor_persona = None

                    for persona in personas_autorizadas:
                        embedding_guardado = persona["embedding"]

                        similitud = reconocedor.match(
                            embedding_actual,
                            embedding_guardado,
                            cv2.FaceRecognizerSF_FR_COSINE,
                        )

                        if (
                            mejor_similitud is None
                            or similitud > mejor_similitud
                        ):
                            mejor_similitud = float(similitud)
                            mejor_persona = persona

                    if (
                        mejor_persona is not None
                        and mejor_similitud is not None
                        and mejor_similitud
                        >= umbrales["recognition"]
                    ):
                        estado_reconocimiento = (
                            "RECONOCIMIENTO: APROBADO - "
                            f"{mejor_persona['name']} "
                            f"{mejor_similitud * 100:.1f}%"
                        )
                        color_reconocimiento = (0, 255, 0)
                        resultado_final = "RESULTADO: AUTORIZADO"
                        color_resultado = (0, 255, 0)

                    else:
                        if mejor_similitud is None:
                            estado_reconocimiento = (
                                "RECONOCIMIENTO: SIN EMBEDDINGS ACTIVOS"
                            )
                        else:
                            estado_reconocimiento = (
                                "RECONOCIMIENTO: RECHAZADO "
                                f"{mejor_similitud * 100:.1f}%"
                            )
                        color_reconocimiento = (0, 0, 255)
                        resultado_final = "RESULTADO: RECHAZADO"
                        color_resultado = (0, 0, 255)

            cv2.rectangle(
                imagen,
                (max(0, x), max(0, y)),
                (
                    min(imagen.shape[1], x + ancho_rostro),
                    min(imagen.shape[0], y + alto_rostro),
                ),
                color_resultado,
                2,
            )

        estados = [
            (estado_supabase, color_supabase),
            (estado_deteccion, color_deteccion),
            (estado_antispoof, color_antispoof),
            (estado_reconocimiento, color_reconocimiento),
            (resultado_final, color_resultado),
        ]

        for posicion, (texto, color) in enumerate(estados):
            cv2.putText(
                imagen,
                texto,
                (20, 30 + posicion * 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )

        cv2.imshow("Prueba SmartGate", imagen)

        tecla = cv2.waitKey(1) & 0xFF

        if tecla == ord("q") or tecla == 27:
            break

finally:
    camara.release()
    cv2.destroyAllWindows()

print("Prueba de cámara finalizada")
