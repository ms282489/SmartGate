"""Prueba los tres modelos utilizando la cámara de la Mac."""

from pathlib import Path

import cv2
import numpy as np
import yaml


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

embeddings = np.load(
    raiz / "data/embeddings.npy"
)

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

                    mejor_similitud = -1.0

                    for embedding_guardado in embeddings:
                        embedding_guardado = (
                            embedding_guardado
                            .reshape(1, -1)
                            .astype(np.float32)
                        )

                        similitud = reconocedor.match(
                            embedding_actual,
                            embedding_guardado,
                            cv2.FaceRecognizerSF_FR_COSINE,
                        )

                        mejor_similitud = max(
                            mejor_similitud,
                            similitud,
                        )

                    if mejor_similitud >= umbrales["recognition"]:
                        estado_reconocimiento = (
                            "RECONOCIMIENTO: APROBADO "
                            f"{mejor_similitud:.2f}"
                        )
                        color_reconocimiento = (0, 255, 0)
                        resultado_final = "RESULTADO: AUTORIZADO"
                        color_resultado = (0, 255, 0)

                    else:
                        estado_reconocimiento = (
                            "RECONOCIMIENTO: RECHAZADO "
                            f"{mejor_similitud:.2f}"
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
