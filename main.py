"""
Archivo principal de SmartGate.

Este archivo se encarga de:

1. Cargar los tres modelos.
2. Preparar la cara de la persona autorizada.
3. Abrir la cámara.
4. Enviar cada imagen al pipeline.
5. Mostrar el resultado.
6. Liberar la cámara al finalizar.
"""

import time

# OpenCV se utiliza para abrir la cámara y leer imágenes.
import cv2

# Archivo que contiene rutas, umbrales y configuración.
import config

# Importar cada uno de los tres módulos del sistema.
from detector_rostros import DetectorRostros
from antispoofing import EvaluadorAntispoofing
from reconocimiento_facial import ReconocedorFacial

# Importar el coordinador de los tres modelos.
from pipeline import PipelineProcesamiento


def cargar_embedding_referencia(detector, reconocedor):
    """
    Cargar la fotografía de la persona autorizada.

    Luego detecta la cara y la transforma en un embedding
    para utilizarla durante las comparaciones.
    """

    # Leer la fotografía configurada en config.py.
    #
    # cv2.imread() devuelve:
    # - Una imagen si pudo abrir el archivo.
    # - None si no pudo abrirlo.
    referencia = cv2.imread( str(config.RUTA_REFERENCIA))

    # Comprobar que la fotografía se haya cargado correctamente.
    if referencia is None:
        raise ValueError(f"No se pudo abrir: {config.RUTA_REFERENCIA}")

    # Buscar caras en la fotografía de referencia usando YuNet.
    rostros = detector.detectar(referencia)

    # La fotografía debe contener exactamente una cara.
    #
    # Si no contiene ninguna cara o contiene varias,
    # no puede utilizarse como referencia.
    if len(rostros) != 1:
        raise ValueError(
            "La referencia debe contener exactamente una cara"
        )

    # Obtener la única cara encontrada.
    rostro_referencia = rostros[0]

    # Convertir la cara de referencia en un embedding.
    #
    # Este vector se calcula una sola vez al iniciar el programa.
    embedding_referencia = reconocedor.obtener_embedding( referencia, rostro_referencia, )

    # Devolver el embedding para utilizarlo en el pipeline.
    return embedding_referencia


def crear_pipeline():
    """
    Cargar los tres modelos y crear el pipeline.
    """

    # Limitar la cantidad de hilos internos utilizados por OpenCV.
    #
    # Esto ayuda a evitar que OpenCV ocupe todos los núcleos
    # disponibles en la Raspberry Pi.
    cv2.setNumThreads(config.HILOS_OPENCV)

    # =====================================================
    # MODELO 1: DETECCIÓN FACIAL
    # =====================================================

    # Crear el detector YuNet.
    detector = DetectorRostros(
        # Ruta del modelo ONNX.
        config.RUTA_DETECTOR,

        # Tamaño inicial esperado para las imágenes.
        (config.ANCHO, config.ALTO),

        # Confianza mínima para aceptar una cara.
        config.UMBRAL_DETECCION,
    )

    # =====================================================
    # MODELO 2: ANTISPOOFING
    # =====================================================

    # Crear el evaluador MiniFASNetV2.
    antispoofing = EvaluadorAntispoofing(
        # Ruta del modelo ONNX.
        config.RUTA_ANTISPOOF,

        # Cuánto se amplía el recorte alrededor de la cara.
        config.ESCALA_RECORTE,

        # Cantidad de hilos internos de ONNX Runtime.
        config.HILOS_ONNX_INTRA,
        config.HILOS_ONNX_INTER,
    )

    # =====================================================
    # MODELO 3: RECONOCIMIENTO FACIAL
    # =====================================================

    # Crear el reconocedor SFace.
    reconocedor = ReconocedorFacial(
        config.RUTA_RECONOCEDOR
    )

    # =====================================================
    # PREPARAR LA PERSONA AUTORIZADA
    # =====================================================

    # Detectar y convertir la cara registrada en un embedding.
    embedding_referencia = cargar_embedding_referencia( detector, reconocedor, )

    # =====================================================
    # CREAR EL PIPELINE
    # =====================================================

    # Entregarle al pipeline:
    #
    # - Los tres módulos.
    # - El embedding autorizado.
    # - Los umbrales de decisión.
    pipeline = PipelineProcesamiento(
        detector=detector,
        antispoofing=antispoofing,
        reconocedor=reconocedor,
        embedding_referencia=embedding_referencia,
        umbral_antispoof=config.UMBRAL_ANTISPOOF,
        umbral_identidad=config.UMBRAL_IDENTIDAD,
    )

    return pipeline


def ejecutar():
    """
    Ejecutar SmartGate hasta que el usuario presione Ctrl+C.
    """

    # Cargar los modelos y preparar el pipeline.
    pipeline = crear_pipeline()

    # Abrir la cámara indicada en config.py.
    #
    # El índice cero normalmente representa la primera cámara.
    camara = cv2.VideoCapture(
        config.INDICE_CAMARA
    )

    # Verificar que la cámara se haya abierto correctamente.
    if not camara.isOpened():

        # Liberarla antes de mostrar el error.
        camara.release()

        raise RuntimeError(
            f"No se pudo abrir la camara "
            f"{config.INDICE_CAMARA}"
        )

    # Solicitar a la cámara el ancho configurado.
    camara.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        config.ANCHO,
    )

    # Solicitar a la cámara el alto configurado.
    camara.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        config.ALTO,
    )

    # Crear el grupo de hilos del pipeline.
    pipeline.iniciar()

    # Este try permite controlar la interrupción con Ctrl+C.
    try:

        # Esperar unos segundos para que la cámara ajuste
        # automáticamente la exposición y el brillo.
        time.sleep(
            config.TIEMPO_ESTABILIZACION_CAMARA
        )

        print(
            "Sistema iniciado. "
            "Presiona Ctrl+C para terminar."
        )

        # Repetir el procesamiento mientras el sistema funcione.
        while True:

            # Capturar una imagen de la cámara.
            #
            # read() devuelve:
            # - ok: indica si la captura funcionó.
            # - imagen: fotograma obtenido.
            ok, imagen = camara.read()

            # Si la cámara no pudo entregar una imagen,
            # detener el programa mostrando un error.
            if not ok:
                raise RuntimeError(
                    "No se pudo obtener una imagen de la camara"
                )

            # Enviar el fotograma al pipeline.
            #
            # Internamente se ejecutan:
            # 1. YuNet.
            # 2. MiniFASNetV2.
            # 3. SFace, si las etapas anteriores fueron aprobadas.
            resultado = pipeline.procesar(imagen)

            # Mostrar el resultado en la consola.
            print(resultado)

            # En el futuro, esta condición podría utilizarse
            # para activar el motor o una salida GPIO.
            if resultado["coincide"]:
                print("Acceso autorizado")

            # Esperar antes de procesar otra imagen.
            time.sleep(
                config.PAUSA_SEGUNDOS
            )

    # Ctrl+C genera una excepción llamada KeyboardInterrupt.
    #
    # Este bloque permite terminar sin mostrar un error largo.
    except KeyboardInterrupt:
        print("Programa detenido por el usuario.")

    # finally se ejecuta siempre:
    #
    # - Si se presiona Ctrl+C.
    # - Si falla la cámara.
    # - Si falla un modelo.
    # - Si ocurre cualquier otro error.
    finally:

        # Esperar las tareas pendientes y cerrar los hilos.
        pipeline.detener()

        # Liberar la cámara para que pueda utilizarla
        # otro programa.
        camara.release()

        # Cerrar posibles ventanas creadas por OpenCV.
        cv2.destroyAllWindows()


# Esta condición permite distinguir entre:
#
# 1. Ejecutar directamente este archivo:
#
#       python main.py
#
# 2. Importarlo desde otro archivo:
#
#       import main
#
# ejecutar() solamente se llama en el primer caso.
if __name__ == "__main__":
    ejecutar()