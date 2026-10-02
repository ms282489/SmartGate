# GPIO 

## Objetivo
El módulo `gpio` encapsula la interacción con los pines físicos de la Raspberry Pi.

Gestiona:
- lectura del final de carrera;
- señalización mediante 4 LEDs;
- pulso de apertura del portón.

El resto del sistema **no accede directamente a `gpiod` ni a los números de pin**.

## Inicialización
`main.py` crea el hilo:

```python
threading.Thread(
    target=gpio_manager,
    args=(gpio_config,),
    name="GPIO"
).start()
```

`gpio_manager(config)`:
1. recibe desde `config.yaml` el chip, los pines y el tiempo de pulso;
2. configura el final de carrera como entrada con detección de ambos flancos;
3. configura LEDs y apertura como salidas;
4. lee una vez el estado inicial del final de carrera y actualiza `gate_closed`;
5. crea e inicia `fc_worker` y `command_worker`;
6. finaliza. Los workers continúan ejecutándose.

## Final de carrera
Existe un único `threading.Event` compartido:

```python
gate_closed
```

Convención:

```text
SET   -> portón cerrado
CLEAR -> portón no cerrado
```

`fc_worker` espera eventos de `gpiod`:

```text
RISING  -> gate_closed.clear()
FALLING -> gate_closed.set()
```

Para consultar el estado desde otro módulo:

```python
from core.sync import gate_closed

if gate_closed.is_set():
    ...
```

## Comandos GPIO
Los módulos externos controlan las salidas mediante las funciones públicas de `gpio_comandos.py`:

```python
from gpio.gpio_comandos import (
    activo,
    procesando,
    aceptado,
    rechazado,
    abrir
)
```

Uso:

```python
activo()       # LED de sistema disponible
procesando()   # LED de procesamiento
aceptado()     # LED de acceso aceptado
rechazado()    # LED de acceso rechazado
abrir()        # genera el pulso de apertura
```

Las funciones únicamente colocan un comando en una `queue.Queue`, por lo que la llamada desde otro hilo es rápida y no manipula directamente los GPIO.

`command_worker` recibe esos comandos y ejecuta la acción física correspondiente.

Para los LEDs siempre deja **un único LED encendido**.

## Regla de integración
Desde otros módulos:

```text
Estado del portón -> leer gate_closed
Cambiar señalización -> llamar activo/procesando/aceptado/rechazado
Abrir portón -> llamar abrir()
```

No se debe utilizar `gpiod` directamente fuera del módulo GPIO.
