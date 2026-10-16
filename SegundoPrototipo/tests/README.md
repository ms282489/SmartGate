# Pruebas de SmartGate en Mac

Estas pruebas comprueban las partes del programa que no necesitan una Raspberry Pi.

Desde la carpeta `SegundoPrototipo`, ejecutar:

```bash
python3 tests/ejecutar_pruebas.py
```

Se comprueba:

- La sintaxis de los archivos Python.
- La existencia de los tres modelos.
- La existencia y contenido de `embeddings.npy`.
- La configuración de telemetría.
- Los estados principales del pipeline.
- Los comandos destinados a GPIO.
- Los eventos enviados a telemetría.
- El resumen serial mediante un puerto simulado.

Estas pruebas no comprueban la cámara, los pines GPIO, el puerto serial físico ni la velocidad real de los modelos. Esas partes deben probarse en la Raspberry Pi.

## Prueba opcional con la cámara de la Mac

Para probar detección, antispoofing y reconocimiento con la cámara:

```bash
PYTHONPATH=app python3 tests/probar_camara.py
```

macOS puede solicitar permiso para que la terminal utilice la cámara. La ventana se cierra presionando `Q` o `Esc`.

Esta prueba no se inicia desde `ejecutar_pruebas.py` porque necesita intervención del usuario y mantiene una ventana abierta.
