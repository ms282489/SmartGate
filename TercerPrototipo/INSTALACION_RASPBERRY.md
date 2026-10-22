# Instalación en Raspberry Pi con Arducam OV5647

Este prototipo utiliza Picamera2 y libcamera. La lógica de detección,
antispoofing, reconocimiento, Supabase, GPIO y telemetría es la misma
que en `SegundoPrototipo`.

## 1. Preparar la cámara

Con la Raspberry apagada, conectar la OV5647 al puerto CSI. En
Raspberry Pi OS Bookworm o Trixie editar:

```bash
sudo nano /boot/firmware/config.txt
```

Configurar:

```text
camera_auto_detect=0

[all]
dtoverlay=ov5647
```

En una Raspberry Pi 5 con la cámara conectada a `CAM0`, usar:

```text
dtoverlay=ov5647,cam0
```

Reiniciar y verificar que aparezca `ov5647`:

```bash
sudo reboot
rpicam-still --list-cameras
```

## 2. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-venv
```

Picamera2 usa los enlaces de libcamera instalados por Raspberry Pi OS.
Por eso el entorno virtual debe conservar acceso a los paquetes del
sistema:

```bash
cd TercerPrototipo
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Probar la cámara

```bash
PYTHONPATH=app python testing/probar_arducam.py
```

El resultado esperado es similar a:

```text
Arducam OV5647 lista: 1280x960, 3 canales BGR
```

## 4. Ejecutar SmartGate

Ejecutar siempre desde la carpeta `TercerPrototipo` para que las rutas
de configuración sean correctas:

```bash
python app/main.py
```

Si la cámara no aparece, revisar el cable CSI, el puerto seleccionado y
el resultado de `rpicam-still --list-cameras` antes de iniciar SmartGate.
