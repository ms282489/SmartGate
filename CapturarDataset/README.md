# Captura del dataset desde macOS por SSH

Este módulo utiliza la cámara CSI de la Raspberry Pi, muestra la vista en el
Mac y guarda fotografías JPEG en la carpeta `dataset` de la raíz de SmartGate.
Las imágenes originales se guardan en la Raspberry, no en el Mac.

## Método recomendado: navegador y túnel SSH

Este modo comprime la vista como JPEG de 640x480 y apunta a 20 FPS. La captura
guardada conserva los 1280x960 originales, de modo que la reducción de calidad
solo afecta a la previsualización. No requiere XQuartz.

### 1. Crear el túnel

Desde Terminal en el Mac:

```bash
ssh -L 8765:127.0.0.1:8765 admin@SmartGate.local
```

También puede utilizarse la dirección IP de la Raspberry en lugar de
`SmartGate.local`.

### 2. Iniciar la captura en la Raspberry

Dentro de esa misma conexión SSH:

```bash
cd ~/Documents/SmartGate
python3 CapturarDataset/capturar_dataset_web.py --nombre real_mateo
```

SmartGate debe estar detenido si está usando la cámara. Una cámara CSI no puede
ser abierta por dos aplicaciones al mismo tiempo.

### 3. Abrir la vista en el Mac

Abrir en Safari o Chrome:

```text
http://localhost:8765
```

Controles:

- `Espacio`: guardar la fotografía completa más reciente.
- Botón `Tomar foto`: alternativa para capturar con el ratón.
- Botón `Finalizar`: guardar lo pendiente, liberar la cámara y cerrar.

Para reducir todavía más el tráfico o la carga de la Raspberry:

```bash
python3 CapturarDataset/capturar_dataset_web.py \
  --nombre real_mateo \
  --vista-ancho 480 \
  --calidad-jpeg 45 \
  --vista-fps 20
```

Los 20 FPS son un objetivo. El valor real depende del modelo de Raspberry, la
red y el costo de codificar JPEG. La página muestra la velocidad generada por
la Raspberry.

## Método alternativo: ventana XQuartz

El script anterior continúa disponible para usar una ventana OpenCV reenviada
por X11:

```bash
ssh -Y admin@SmartGate.local
cd ~/Documents/SmartGate
python3 CapturarDataset/capturar_dataset.py --nombre real_mateo
```

Este método requiere XQuartz y puede funcionar a muy pocos FPS porque X11 no
está diseñado para transportar video. Controles:

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

## Prueba sin cámara

La creación de carpetas, numeración y escritura JPEG puede verificarse con:

```bash
python3 CapturarDataset/testing/probar_captura.py
python3 CapturarDataset/testing/probar_captura_web.py
```

## Solución de problemas

- El navegador no conecta: comprobar que SSH se inició con `-L 8765:...` y que
  el script web continúa ejecutándose en la Raspberry.
- La vista web no alcanza 20 FPS: usar `--vista-ancho 480 --calidad-jpeg 45`.
- `no hay una pantalla disponible`: solo afecta al método XQuartz; iniciar
  XQuartz y reconectar con `ssh -Y`.
- La ventana XQuartz va lenta: usar el método del navegador.
- `No se pudo abrir la camara`: detener el servicio de SmartGate que está
  usando la cámara y volver a intentar.
- Al salir, esperar el mensaje de finalización; el programa termina de escribir
  todas las fotografías pendientes antes de cerrar.
