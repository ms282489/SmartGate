# Pruebas de SmartGate

Estas pruebas comprueban las partes del programa que no necesitan una Raspberry Pi.

Desde la carpeta `TercerPrototipo`, ejecutar:

```bash
python3 testing/ejecutar_pruebas.py
```

Se comprueba:

- La sintaxis de los archivos Python.
- La existencia de los tres modelos.
- La existencia y contenido de `embeddings.npy`.
- La configuración de telemetría.
- La pausa posterior a una autorización y su reactivación automática.
- La entrada del detector a IDLE tras 5 segundos sin rostros.
- El sondeo de bajo consumo y el escalado de coordenadas de YuNet.
- Los estados principales del pipeline.
- Los comandos destinados a GPIO.
- Los eventos enviados a telemetría.
- El resumen serial mediante un puerto simulado.

Estas pruebas no comprueban la cámara, los pines GPIO, el puerto serial físico ni la velocidad real de los modelos. Esas partes deben probarse en la Raspberry Pi.

## Cadencia configurada del detector

La sección `detection` de `config/config.yaml` controla el rendimiento. YuNet
busca sin una pausa artificial mientras el sistema está activo. Después de 5
segundos sin rostros pasa a IDLE y sondea cada 0,2 segundos. Al encontrar una
cara procesa ese mismo cuadro. Después de autorizar una identidad y volver a
IDLE, el detector permanece deshabilitado durante 10 segundos para no repetir
el acceso de la misma persona.

La detección inicial se ejecuta sobre una copia de 640x480 para reducir el
tiempo de inferencia. El antispoofing y el reconocimiento conservan la imagen
original de 1280x960.

## Prueba rápida de la Arducam OV5647

Esta prueba abre Picamera2, captura cuadros y comprueba la resolución
sin iniciar los modelos ni necesitar una pantalla:

```bash
PYTHONPATH=app python3 testing/probar_arducam.py
```

## Prueba completa con cámara y modelos

Para probar detección, antispoofing y reconocimiento con la cámara:

```bash
PYTHONPATH=app python3 testing/probar_camara.py
```

La prueba completa necesita una sesión gráfica. La ventana se cierra
presionando `Q` o `Esc`.

Mientras la ventana está abierta, la prueba actualiza desde Supabase
las personas activas cada 2 segundos y procesa las fotografías nuevas
cada 10 segundos. El estado de la conexión y la cantidad de embeddings
activos aparecen sobre la imagen.

Esta prueba no se inicia desde `ejecutar_pruebas.py` porque necesita intervención del usuario y mantiene una ventana abierta.
