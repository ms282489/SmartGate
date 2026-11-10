# Captura del dataset desde macOS por SSH

Este módulo utiliza la cámara CSI de la Raspberry Pi, muestra la vista en el
Mac y guarda fotografías JPEG en la carpeta `dataset` de la raíz de SmartGate.
La ventana viaja mediante el reenvío gráfico de SSH; las imágenes originales
se guardan en la Raspberry, no en el Mac.

## 1. Preparar el Mac

Instalar [XQuartz](https://www.xquartz.org/) y abrirlo antes de iniciar la
conexión SSH. Después de la instalación puede ser necesario cerrar la sesión de
macOS y volver a entrar.

## 2. Conectarse a la Raspberry

Desde Terminal en el Mac:

```bash
ssh -Y usuario@direccion-de-la-raspberry
```

`-Y` habilita el reenvío de la ventana de OpenCV hacia XQuartz. Para comprobar
que SSH preparó la pantalla remota:

```bash
echo $DISPLAY
```

Debe aparecer un valor similar a `localhost:10.0`. Si está vacío, la ventana no
podrá abrirse. En la Raspberry deben estar instalados `xauth`, Picamera2,
OpenCV y PyYAML.

## 3. Ejecutar la captura

Detener primero SmartGate si está usando la cámara. Una cámara CSI no puede ser
abierta por las dos aplicaciones al mismo tiempo.

Desde la raíz del repositorio:

```bash
python3 CapturarDataset/capturar_dataset.py --nombre real_mateo
```

La ventana aparecerá en el Mac. Controles:

- `Espacio`: guardar la fotografía actual.
- `S`: pausar las capturas sin cerrar la vista.
- `N`: escribir otro nombre de sesión en la terminal.
- `Q` o `Esc`: guardar lo pendiente y salir.

Las fotografías se guardan sin textos ni reducción de resolución en:

```text
SmartGate/dataset/real_mateo/real_mateo_0001.jpg
SmartGate/dataset/real_mateo/real_mateo_0002.jpg
```

Para reunir la clase falsa del entrenamiento puede iniciarse otra sesión, por
ejemplo:

```bash
python3 CapturarDataset/capturar_dataset.py --nombre spoof_pantalla_mateo
```

La vista se limita a 10 FPS para no saturar SSH, pero la cámara mantiene 30 FPS
y cada pulsación guarda el cuadro completo más reciente. Los valores pueden
cambiarse con `--vista-fps` y `--fps`.

## Prueba sin cámara

La creación de carpetas, numeración y escritura JPEG puede verificarse con:

```bash
python3 CapturarDataset/testing/probar_captura.py
```

## Solución de problemas

- `no hay una pantalla disponible`: iniciar XQuartz y reconectar con `ssh -Y`.
- La ventana va lenta: ejecutar con `--vista-fps 5`.
- `No se pudo abrir la camara`: detener el servicio de SmartGate que está
  usando la cámara y volver a intentar.
- Al salir, esperar el mensaje de finalización; el programa termina de escribir
  todas las fotografías pendientes antes de cerrar.
