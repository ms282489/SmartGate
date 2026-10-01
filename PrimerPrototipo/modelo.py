from pathlib import Path
import time

import cv2                  # Procesamiento de imágenes, YuNet y SFace.
import numpy as np          # Operaciones con matrices y resultados del modelo.
import onnxruntime as ort   # Ejecuta el modelo de antispoofing.



# ============================================================
# 1. CONFIGURACIÓN: ACÁ CAMBIÁS ARCHIVOS Y PARÁMETROS
# ============================================================

# Carpeta donde está este archivo Python.
# Así las rutas funcionan aunque ejecutes el programa desde otra carpeta.
CARPETA = Path(__file__).resolve().parent

# >>> ACÁ INDICÁS LA FOTO DE LA PERSONA AUTORIZADA <<<
RUTA_REFERENCIA = CARPETA / "test.jpeg"

# >>> ACÁ INDICÁS LOS ARCHIVOS DE LOS MODELOS <<<
RUTA_DETECTOR = CARPETA / "models" / "face_detection_yunet_2023mar.onnx"
RUTA_ANTISPOOF = CARPETA / "models" / "MiniFASNetV2.onnx"
RUTA_RECONOCEDOR = CARPETA / "models" / "face_recognition_sface_2021dec.onnx"

# Tamaño de las imágenes que entrega la cámara.
ANCHO = 640
ALTO = 480

# Tiempo de descanso entre evaluaciones.
# La duración de cada vuelta será: procesamiento + esta pausa.
PAUSA_SEGUNDOS = 0.3

# Valores de ejemplo. Hay que calibrarlos usando la cámara real.
UMBRAL_DETECCION = 0.85
UMBRAL_ANTISPOOF = 0.90
UMBRAL_IDENTIDAD = 0.50

# MiniFASNetV2 utiliza un recorte ampliado alrededor del rostro.
# Para el export MiniFASNetV1SE de la entrega anterior se utiliza 4.0.
ESCALA_RECORTE = 2.7


# ============================================================
# 2. CARGAR LOS MODELOS UNA SOLA VEZ
# ============================================================

# Buscar un rostro y obtener su posición y puntos faciales.
detector = cv2.FaceDetectorYN.create(
    str(RUTA_DETECTOR),
    "",
    (ANCHO, ALTO),
    score_threshold=UMBRAL_DETECCION
)

# Alinear el rostro y convertirlo en un vector para comparar identidades.
reconocedor = cv2.FaceRecognizerSF.create(
    str(RUTA_RECONOCEDOR),
    ""
)

# Ejecutar MiniFASNet sobre la CPU.
# Limitamos sus hilos como configuración inicial para la Raspberry.
opciones = ort.SessionOptions()
opciones.intra_op_num_threads = 2
opciones.inter_op_num_threads = 1

antispoof = ort.InferenceSession(
    str(RUTA_ANTISPOOF),
    sess_options=opciones,
    providers=["CPUExecutionProvider"]
)

# El modelo ONNX tiene un nombre para su entrada.
# Lo consultamos para no tener que escribir ese nombre manualmente.
nombre_entrada = antispoof.get_inputs()[0].name

# Limitar también los hilos usados por OpenCV.
cv2.setNumThreads(2)


# ============================================================
# 3. FUNCIONES DE PROCESAMIENTO
# ============================================================

def detectar_rostros(imagen):
    """
    Recibe:
        Una imagen en formato BGR, el formato habitual de OpenCV.

    Devuelve:
        Los rostros detectados, o una lista vacía si no encuentra ninguno.

    Cada rostro contiene:
        - Posición y tamaño de la cara.
        - Cinco puntos faciales para alinearla.
        - Puntuación de detección.
    """

    alto, ancho = imagen.shape[:2]

    # La foto de referencia puede tener otro tamaño que la cámara.
    # Por eso ajustamos el detector al tamaño de cada imagen.
    detector.setInputSize((ancho, alto))

    _, rostros = detector.detect(imagen)

    if rostros is None:
        return []

    return rostros


def obtener_embedding(imagen, rostro):
    """
    Recibe:
        Una imagen y uno de los rostros encontrados por YuNet.

    Devuelve:
        Un embedding: un vector numérico que representa ese rostro.

    El embedding permite comparar caras sin comparar directamente
    todos los píxeles de las fotografías.
    """

    # Alinear significa acomodar la cara usando ojos, nariz y boca.
    # Esto reduce diferencias causadas por inclinación y posición.
    cara_alineada = reconocedor.alignCrop(imagen, rostro)

    # SFace transforma esa cara alineada en un vector numérico.
    embedding = reconocedor.feature(cara_alineada)

    return embedding


def evaluar_antispoof(imagen, rostro):
    """
    Recibe:
        La imagen original y la ubicación del rostro.

    Devuelve:
        Una puntuación entre 0 y 1 para la clase 'rostro real'.

    Esta preparación corresponde al MiniFASNet ONNX de la entrega
    anterior. Otros archivos pueden necesitar otra normalización
    o tener las clases en otro orden.
    """

    alto, ancho = imagen.shape[:2]

    # Los primeros cuatro valores de YuNet son:
    # x, y, ancho de la cara y alto de la cara.
    x, y, w, h = map(int, rostro[:4])

    if w <= 0 or h <= 0:
        return 0.0

    # Ampliamos la región porque MiniFASNet utiliza contexto
    # alrededor de la cara, no solamente una cara recortada al ras.
    escala = min(
        ESCALA_RECORTE,
        (ancho - 1) / w,
        (alto - 1) / h
    )

    centro_x = x + w / 2
    centro_y = y + h / 2

    # Limitamos las coordenadas para no salirnos de la imagen.
    izquierda = max(0, int(centro_x - w * escala / 2))
    derecha = min(ancho - 1, int(centro_x + w * escala / 2))
    arriba = max(0, int(centro_y - h * escala / 2))
    abajo = min(alto - 1, int(centro_y + h * escala / 2))

    recorte = imagen[arriba:abajo + 1, izquierda:derecha + 1]

    if recorte.size == 0:
        return 0.0

    # Este modelo recibe imágenes de 80 × 80 píxeles.
    cara = cv2.resize(recorte, (80, 80))

    # Este export espera números float32 en el rango 0–255.
    # No dividimos por 255 y mantenemos el orden de colores BGR.
    cara = cara.astype(np.float32)

    # Pasamos de:
    #   alto × ancho × canales
    # a:
    #   cantidad de imágenes × canales × alto × ancho
    #
    # El resultado tiene tamaño: 1 × 3 × 80 × 80.
    tensor = np.ascontiguousarray(
        cara.transpose(2, 0, 1)[None]
    )

    # Ejecutar la red neuronal.
    salida = antispoof.run(
        None,
        {nombre_entrada: tensor}
    )[0].reshape(-1)

    # Este export debe devolver tres valores numéricos válidos.
    if salida.size != 3 or not np.isfinite(salida).all():
        return 0.0

    # Softmax transforma las salidas en puntuaciones que suman 1.
    # Restar el máximo evita problemas numéricos al calcular exp().
    puntuaciones = np.exp(salida - salida.max())
    puntuaciones /= puntuaciones.sum()

    # En este modelo específico, el índice 1 es la clase 'real'.
    # No debe interpretarse como una garantía de seguridad.
    return float(puntuaciones[1])


def analizar_imagen(imagen, embedding_referencia):
    """
    Ejecuta las tres etapas para una imagen de la cámara.

    Devuelve un diccionario con:
        estado: explicación del resultado.
        coincide: si pasó ambos umbrales en este fotograma.
        antispoof: puntuación de rostro real, cuando se calculó.
        similitud: comparación de identidad, cuando se calculó.
    """

    resultado = {
        "estado": "Sin rostro",
        "coincide": False,
        "antispoof": None,
        "similitud": None
    }

    # ETAPA 1: buscar una cara.
    rostros = detectar_rostros(imagen)

    if len(rostros) == 0:
        return resultado

    # Para simplificar, solo procesamos una persona por vez.
    if len(rostros) > 1:
        resultado["estado"] = "Hay varias caras"
        return resultado

    rostro = rostros[0]

    # ETAPA 2: evaluar si supera el antispoofing.
    puntuacion_real = evaluar_antispoof(imagen, rostro)
    resultado["antispoof"] = puntuacion_real

    if puntuacion_real < UMBRAL_ANTISPOOF:
        resultado["estado"] = "No supera el antispoofing"
        return resultado

    # ETAPA 3: comparar identidad.
    # Esta parte se ejecuta solamente si pasó el antispoofing.
    embedding_actual = obtener_embedding(imagen, rostro)

    similitud = float(reconocedor.match(
        embedding_referencia,
        embedding_actual,
        cv2.FaceRecognizerSF_FR_COSINE
    ))

    resultado["similitud"] = similitud

    # La similitud coseno NO es un porcentaje de certeza.
    if np.isfinite(similitud) and similitud >= UMBRAL_IDENTIDAD:
        resultado["estado"] = "Coincide con la persona registrada"
        resultado["coincide"] = True
    else:
        resultado["estado"] = "Persona desconocida"

    return resultado


# ============================================================
# 4. CARGAR LA IMAGEN DE REFERENCIA
# ============================================================

# >>> ACÁ SE LEE EFECTIVAMENTE LA FOTO DEL DISCO <<<
referencia = cv2.imread(str(RUTA_REFERENCIA))

if referencia is None:
    raise ValueError(f"No se pudo abrir: {RUTA_REFERENCIA}")

rostros_referencia = detectar_rostros(referencia)

if len(rostros_referencia) != 1:
    raise ValueError("La referencia debe contener exactamente una cara")

# Calculamos el embedding una sola vez.
# Después lo reutilizamos en todas las comparaciones.
embedding_referencia = obtener_embedding(
    referencia,
    rostros_referencia[0]
)


# ============================================================
# 5. INICIAR LA CÁMARA DEL MAC
# ============================================================

camara = cv2.VideoCapture(0)

if not camara.isOpened():
    camara.release()
    raise RuntimeError(
        "No se pudo abrir la cámara. Revisá los permisos de macOS."
    )

camara.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO)
camara.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO)

# ============================================================
# 6. REPETIR LA EVALUACIÓN HASTA PRESIONAR CTRL+C
# ============================================================

try:
    # Dar tiempo a la cámara para estabilizar la exposición.
    time.sleep(2)

    print("Sistema iniciado. Presioná Ctrl+C para terminar.")

    while True:
        # >>> ACÁ SE OBTIENE UNA NUEVA IMAGEN DE LA CÁMARA <<<
        #imagen = camara.capture_array()

        # OpenCV devuelve si la captura funcionó y la imagen obtenida.
        ok, imagen = camara.read()

        if not ok:
            raise RuntimeError("No se pudo obtener una imagen de la cámara")

        # La función devuelve un resultado que después podés
        # utilizar para un LED, una interfaz o una lógica de acceso.
        resultado = analizar_imagen(
            imagen,
            embedding_referencia
        )

        # Por ahora, simplemente mostrarlo en la consola.
        print(resultado)

        # Reducir la frecuencia de procesamiento.
        time.sleep(PAUSA_SEGUNDOS)

except KeyboardInterrupt:
    print("Programa detenido.")

finally:
    camara.release()
    cv2.destroyAllWindows()