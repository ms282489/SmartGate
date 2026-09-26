# Arquitectura de control y pipeline — SmartGate

## 1. Objetivo de la arquitectura

El sistema SmartGate se ejecutará sobre Raspberry Pi OS y será iniciado automáticamente luego del arranque de la placa mediante un servicio configurado en `systemd`. Una vez completado el proceso de boot de la Raspberry Pi, `systemd` lanzará la aplicación principal `main.py`, la cual permanecerá en ejecución como proceso principal del sistema SmartGate.

La aplicación principal tendrá como objetivo inicializar los recursos necesarios para el funcionamiento del sistema y lanzar los distintos hilos responsables del procesamiento de imágenes, supervisión del estado físico del portón y control general del pipeline.

La arquitectura se plantea como un sistema concurrente dirigido por eventos. Los modelos de machine learning no se ejecutan permanentemente en paralelo, sino que forman un pipeline secuencial en el cual cada etapa habilita a la siguiente cuando se cumplen determinadas condiciones.

El sistema deberá garantizar que:

- El pipeline de visión solo pueda iniciar nuevos ciclos cuando el portón esté cerrado.
- Solo exista una muestra o usuario activo dentro del pipeline en cada instante.
- Modelo 1 no vuelva a buscar un nuevo usuario hasta que el procesamiento del usuario anterior haya finalizado.
- Los hilos permanezcan bloqueados cuando no tengan trabajo pendiente.
- Los buffers compartidos mantengan un estado conocido.
- Cada etapa consuma el buffer correspondiente antes de regresar a su estado `IDLE`.
- Los cambios físicos del portón puedan bloquear inmediatamente el inicio de nuevos ciclos.
- Ante una interrupción asíncrona del flujo normal, el gestor pueda esperar un estado seguro y normalizar los recursos compartidos.

---

# 2. Arquitectura general

```text
                              Raspberry Pi OS
                                     │
                                  systemd
                                     │
                         arranque automático
                           luego del boot
                                     │
                                     ▼
                              ┌─────────────┐
                              │   main.py   │
                              └──────┬──────┘
                                     │
           Inicialización de modelos, GPIO, hilos,
           Events, Locks, buffers y configuración
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
┌───────────────┐           ┌────────────────┐            ┌───────────────┐
│ GPIO FC Thread│──────────►│Pipeline Manager│            │  Telemetría   │
└───────┬───────┘           └───────┬────────┘            └───────────────┘
        │                            │
        │ gate_closed               │ detection_enabled
        │                            │
        ▼                            ▼
                                ┌───────────┐
                                │ MODELO 1  │
                                │ Detección │
                                └─────┬─────┘
                                      │
                              candidato válido
                                      │
                         detection_enabled.clear()
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
                     BUFFER 1                BUFFER 2
                    Antispoofing            Reconocimiento
                          │                       │
                    buffer1_ready                 │
                          │                       │
                          ▼                       │
                     ┌───────────┐                │
                     │ MODELO 2  │                │
                     │ Antispoof │                │
                     └─────┬─────┘                │
                           │                      │
                    ┌──────┴──────┐               │
                    │             │               │
                  SPOOF          REAL             │
                    │             │               │
                    ▼             ▼               │
             descartar B2   recognition_ready    │
                    │             │               │
                    │             └──────┬────────┘
                    │                    ▼
                    │               ┌───────────┐
                    │               │ MODELO 3  │
                    │               │ Recognition│
                    │               └─────┬─────┘
                    │                     │
                    │              ┌──────┴──────┐
                    │              │             │
                    ▼            DENIED       AUTHORIZED
             habilitar M1          │             │
                                   ▼             ▼
                              habilitar M1   accionar portón
                                                 │
                                                 ▼
                                            esperar RISING
                                                 │
                                                 ▼
                                          esperar FALLING
                                                 │
                                                 ▼
                                           habilitar M1
```

La lógica general se divide en cuatro bloques:

1. Supervisión física del portón mediante GPIO.
2. Gestión del estado global del pipeline.
3. Ejecución secuencial de los modelos.
4. Gestión de buffers y sincronización entre hilos.

---

# 3. Arranque del sistema

`systemd` será responsable de iniciar automáticamente SmartGate luego de que Raspberry Pi OS complete el proceso de boot. El servicio configurado para SmartGate ejecutará `main.py` sin requerir intervención manual y podrá además reiniciar la aplicación ante determinados fallos.

La función `main()` no realizará directamente las inferencias. Su responsabilidad será preparar el entorno de ejecución.

Secuencia conceptual:

```text
Encendido Raspberry Pi
   │
   ▼
Boot Raspberry Pi OS
   │
   ▼
systemd
   │
   ▼
smartgate.service
   │
   ▼
main.py
   │
   ├── cargar configuración
   ├── inicializar logging
   ├── inicializar GPIO
   ├── leer estado inicial del portón
   ├── cargar modelos ML
   ├── cargar embeddings
   ├── crear buffers
   ├── crear Locks
   ├── crear Events
   ├── crear hilos
   └── iniciar hilos
```

Una vez inicializados los hilos, el procesamiento se realizará mediante sincronización entre éstos y no mediante un bucle central que consulte continuamente el estado del sistema.

---

# 4. Estado físico del portón

El sistema utilizará una entrada GPIO asociada al final de carrera de cierre.

La lógica eléctrica considerada será:

```text
GPIO LOW   → portón cerrado
GPIO HIGH  → portón abierto
```

Por lo tanto:

```text
RISING EDGE
LOW → HIGH
Portón se abre.

FALLING EDGE
HIGH → LOW
Portón alcanza la posición de cerrado.
```

Raspberry Pi OS gestionará la interrupción física mediante el controlador GPIO del kernel. La aplicación recibirá los eventos de flanco utilizando la interfaz GPIO del sistema.

El hilo encargado del GPIO permanecerá bloqueado esperando un evento de flanco y solamente se ejecutará cuando éste ocurra.

```text
Cambio físico GPIO
       │
       ▼
IRQ hardware
       │
       ▼
Kernel Linux
       │
       ▼
Edge Event
       │
       ▼
GPIO Thread
```

El código asociado al evento deberá ser mínimo. No realizará inferencias ni accederá directamente a los buffers del pipeline.

Su función será actualizar el estado físico del portón y notificar al gestor.

---

# 5. Estado del portón

Se utilizará un objeto de sincronización para representar el estado físico:

```python
gate_closed = threading.Event()
```

Convención:

```text
gate_closed SET
    Portón cerrado.

gate_closed CLEAR
    Portón abierto.
```

Al producirse un `FALLING EDGE`:

```text
gate_closed.set()
```

Al producirse un `RISING EDGE`:

```text
gate_closed.clear()
```

Al arrancar el sistema deberá leerse directamente el nivel del pin, ya que puede no haberse producido todavía ningún flanco.

---

# 6. Gestor del pipeline

El `Pipeline Manager` será responsable de conocer el estado global del procesamiento y decidir cuándo Modelo 1 puede buscar un nuevo usuario.

No se utilizarán señales separadas `pipeline_enabled` y `pipeline_free`. El gestor mantendrá internamente el estado lógico del pipeline, evitando duplicar información mediante múltiples flags globales.

Conceptualmente podrá manejar estados como:

```text
IDLE
PROCESSING
WAIT_GATE_OPEN
WAIT_GATE_CLOSE
CLEANING
```

Estos estados no tienen por qué implementarse como `threading.Event`, ya que pertenecen a la lógica interna del gestor.

La señal externa utilizada para controlar Modelo 1 será:

```python
detection_enabled = threading.Event()
```

Convención:

```text
SET
Modelo 1 puede buscar un nuevo usuario.

CLEAR
Modelo 1 permanece bloqueado.
```

El `Pipeline Manager` será el único responsable de ejecutar:

```text
detection_enabled.set()
```

cuando corresponda permitir un nuevo ciclo.

Modelo 1 podrá procesar nuevos candidatos solamente cuando:

```text
gate_closed = SET
detection_enabled = SET
```

Cuando Modelo 1 detecta un usuario válido:

```text
detection_enabled.clear()
```

y permanece bloqueado hasta que el gestor determine que el procesamiento de dicho usuario ha finalizado.

Esto garantiza que solamente exista un usuario activo dentro del pipeline y evita procesar repetidamente múltiples frames de una misma persona.

---

# 7. Flujo normal de Modelo 1

Modelo 1 será la entrada al pipeline.

Su hilo permanecerá bloqueado mediante:

```text
detection_enabled.wait()
```

mientras no pueda iniciarse un nuevo ciclo.

Su funcionamiento conceptual será:

```text
Esperar detection_enabled
          │
          ▼
Capturar frame
          │
          ▼
Ejecutar detección
          │
          ▼
¿rostro candidato?
    │              │
   NO             SÍ
    │              │
 repetir           ▼
           detection_enabled.clear()
                   │
                   ▼
            generar Buffer 1
            generar Buffer 2
                   │
                   ▼
          notificar Modelo 2
                   │
                   ▼
          Modelo 1 vuelve a esperar
```

Una vez aceptado un rostro candidato, Modelo 1 no vuelve a buscar otro usuario hasta recibir una nueva habilitación explícita del gestor.

---

# 8. Buffers generados por Modelo 1

Modelo 1 generará dos salidas asociadas a la misma muestra:

```text
BUFFER 1
Imagen o preprocesamiento destinado a antispoofing.

BUFFER 2
Imagen o preprocesamiento destinado a reconocimiento.
```

Cada muestra deberá contener información suficiente para identificar su origen.

Ejemplo conceptual:

```text
FaceSample

frame_id
timestamp
antispoof_image
recognition_image
metadata
```

Al existir una única muestra activa, Modelo 1 no podrá sobrescribir estos buffers antes de que termine el procesamiento correspondiente.

---

# 9. Protección de buffers

Cada buffer será protegido mediante un `Lock`.

```python
buffer1_lock = threading.Lock()
buffer2_lock = threading.Lock()
```

El `Lock` protege el acceso concurrente al contenido.

No representa disponibilidad ni estado lógico del pipeline.

Ejemplo de escritura:

```text
Tomar Lock
   │
   ▼
Escribir buffer
   │
   ▼
Liberar Lock
   │
   ▼
Notificar consumidor
```

El consumidor no deberá ser notificado hasta que la escritura haya finalizado completamente.

---

# 10. Señal de Buffer 1

Una vez que Modelo 1 haya completado ambos buffers podrá notificar a Modelo 2 mediante:

```python
buffer1_ready = threading.Event()
```

La secuencia será:

```text
Modelo 1
   │
   ├── genera Buffer 1
   ├── genera Buffer 2
   │
   ▼
buffer1_ready.set()
   │
   ▼
Modelo 2 despierta
```

Esto permite simplificar la sincronización: si Modelo 2 recibe `buffer1_ready`, se asume por contrato que tanto Buffer 1 como Buffer 2 correspondientes a esa muestra ya fueron generados correctamente.

---

# 11. Modelo 2 — Antispoofing

Modelo 2 permanecerá normalmente bloqueado en:

```text
buffer1_ready.wait()
```

Al despertar:

```text
Modelo 2
   │
   ▼
RUNNING
   │
   ▼
consumir Buffer 1
   │
   ▼
buffer1_ready.clear()
   │
   ▼
ejecutar antispoof
```

Una vez consumido Buffer 1, éste queda disponible o vacío.

El modelo deberá producir uno de dos resultados:

```text
REAL
SPOOF
```

---

# 12. Antispoofing negativo

Si el resultado es `SPOOF`, Modelo 3 no será ejecutado.

En este caso:

```text
Buffer 1 → ya consumido
Buffer 2 → todavía contiene la muestra
```

Por lo tanto se deberá descartar explícitamente Buffer 2.

La secuencia será:

```text
SPOOF
  │
  ▼
limpiar Buffer 2
  │
  ▼
Modelo 2 → IDLE
  │
  ▼
notificar resultado al gestor
  │
  ▼
Pipeline Manager → IDLE
  │
  ▼
detection_enabled.set()
```

El gestor no necesita realizar una limpieza completa si los recursos involucrados ya quedaron correctamente normalizados.

---

# 13. Antispoofing válido

Si el resultado es `REAL`, Modelo 2 habilitará el siguiente módulo mediante:

```python
recognition_ready = threading.Event()
```

Secuencia:

```text
REAL
  │
  ▼
recognition_ready.set()
  │
  ▼
Modelo 2 → IDLE
```

Modelo 1 continúa bloqueado durante todo este proceso.

No se requiere una señal adicional `antispoof_ok`, ya que `recognition_ready` implica que:

```text
Antispoofing fue válido
        Y
Buffer 2 está disponible
```

---

# 14. Modelo 3 — Reconocimiento

Modelo 3 permanecerá bloqueado mediante:

```text
recognition_ready.wait()
```

Cuando dicha señal se activa:

```text
Modelo 3
   │
   ▼
RUNNING
   │
   ▼
consumir Buffer 2
   │
   ▼
recognition_ready.clear()
   │
   ▼
generar embedding
   │
   ▼
comparar con embeddings conocidos
   │
   ▼
AUTHORIZED / DENIED
```

Al consumir Buffer 2, dicho recurso queda vacío.

Modelo 3 regresará posteriormente a `IDLE`.

---

# 15. Usuario no autorizado

Si reconocimiento produce:

```text
DENIED / UNKNOWN
```

en condiciones normales:

```text
Buffer 1 = vacío
Buffer 2 = vacío

Modelo 1 = bloqueado
Modelo 2 = IDLE
Modelo 3 = IDLE

buffer1_ready     = CLEAR
recognition_ready = CLEAR
```

Por lo tanto no es necesario realizar una limpieza global.

Modelo 3 notificará el resultado al gestor:

```text
DENIED
   │
   ▼
Pipeline Manager → IDLE
   │
   ▼
detection_enabled.set()
```

Modelo 1 podrá comenzar a buscar un nuevo usuario.

---

# 16. Usuario autorizado y accionamiento del portón

Si el resultado es:

```text
AUTHORIZED
```

Modelo 1 no será habilitado nuevamente.

El gestor pasará al estado conceptual:

```text
WAIT_GATE_OPEN
```

y generará la orden física hacia el automatismo.

La salida de accionamiento permanecerá en `HIGH` durante un período fijo:

```text
AUTHORIZED
     │
     ▼
GPIO accionamiento = HIGH
     │
     │ tiempo fijo
     ▼
GPIO accionamiento = LOW
```

Durante toda esta secuencia:

```text
detection_enabled = CLEAR
```

Aunque los buffers ya estén vacíos y los modelos hayan regresado a `IDLE`, el sistema no deberá procesar otro usuario.

La confirmación de apertura se obtendrá mediante el final de carrera y no mediante el tiempo transcurrido desde el pulso.

---

# 17. Rising Edge — portón abierto

Luego de una autorización válida, el sistema espera:

```text
RISING EDGE
LOW → HIGH
```

Esto confirma que el portón abandonó la posición de cerrado.

La transición normal será:

```text
WAIT_GATE_OPEN
      │
      ▼
RISING
      │
      ▼
gate_closed.clear()
      │
      ▼
WAIT_GATE_CLOSE
```

En este escenario normal:

```text
Model1 = bloqueado
Model2 = IDLE
Model3 = IDLE
Buffers = vacíos
```

por lo que no es necesario realizar nuevamente una limpieza completa del pipeline.

El sistema permanece bloqueado esperando el cierre físico del portón.

---

# 18. Falling Edge — portón cerrado

Cuando el portón regresa a la posición de cierre:

```text
FALLING EDGE
HIGH → LOW
```

se actualiza:

```text
gate_closed.set()
```

Como el pipeline ya se encuentra vacío y los modelos están en `IDLE`, el gestor solamente debe reanudar la detección.

```text
WAIT_GATE_CLOSE
       │
       ▼
FALLING
       │
       ▼
gate_closed.set()
       │
       ▼
Pipeline Manager → IDLE
       │
       ▼
detection_enabled.set()
```

No se requiere borrar nuevamente buffers ni normalizar señales, ya que esto ocurrió naturalmente durante el procesamiento anterior.

---

# 19. Rising Edge asíncrono

Debe contemplarse también el caso en que aparezca un `RISING EDGE` fuera del flujo esperado.

Por ejemplo, el portón puede comenzar a abrir mientras algún modelo todavía está trabajando o sin que el sistema se encuentre en `WAIT_GATE_OPEN`.

En este caso:

```text
RISING inesperado
       │
       ▼
gate_closed.clear()
       │
       ▼
detection_enabled.clear()
       │
       ▼
Pipeline Manager → CLEANING
```

El gestor deberá esperar que los módulos lleguen a un punto seguro:

```text
model1_idle.wait()
model2_idle.wait()
model3_idle.wait()
```

y posteriormente comprobar y normalizar los recursos compartidos:

```text
vaciar Buffer 1 si corresponde
vaciar Buffer 2 si corresponde
clear buffer1_ready
clear recognition_ready
```

Una vez alcanzado un estado conocido:

```text
Pipeline Manager → WAIT_GATE_CLOSE
```

El sistema permanecerá bloqueado hasta recibir un `FALLING EDGE`.

La limpieza global queda, por tanto, reservada principalmente para eventos asíncronos, fallos, reinicializaciones o estados inesperados.

---

# 20. Estados IDLE de los modelos

Cada hilo asociado a un modelo mantendrá un estado que permita al gestor determinar cuándo es seguro intervenir los recursos.

Se utilizarán:

```python
model1_idle = threading.Event()
model2_idle = threading.Event()
model3_idle = threading.Event()
```

Convención:

```text
SET
Modelo IDLE.

CLEAR
Modelo RUNNING.
```

Al comenzar una inferencia:

```text
modelX_idle.clear()
```

Al terminar y regresar a su espera:

```text
modelX_idle.set()
```

Estos eventos no controlan el flujo normal entre modelos.

Su función principal será permitir que el `Pipeline Manager` espere un punto seguro ante una intervención global.

---

# 21. Señales principales del MVP

La primera versión podrá funcionar con un conjunto reducido de señales:

```text
gate_closed
    Estado físico del portón.

detection_enabled
    Habilitación del Modelo 1.

buffer1_ready
    Modelo 1 completó la muestra y Modelo 2 puede consumir Buffer 1.

recognition_ready
    Antispoofing fue válido y Modelo 3 puede consumir Buffer 2.

model1_idle
model2_idle
model3_idle
    Estado seguro de cada hilo.

shutdown
    Finalización global del sistema.
```

No será necesario mantener simultáneamente:

```text
pipeline_enabled
pipeline_free
buffer2_ready
antispoof_ok
```

ya que su información puede deducirse del estado interno del gestor o de las señales ya existentes.

---

# 22. Flujo normal completo

## Usuario rechazado por antispoofing

```text
Modelo 1
   │
   ▼
genera B1 + B2
   │
   ▼
bloquea detección
   │
   ▼
Modelo 2
   │
   ▼
SPOOF
   │
   ├── B1 ya consumido
   └── borrar B2
   │
   ▼
notificar gestor
   │
   ▼
detection_enabled.set()
```

## Usuario no reconocido

```text
Modelo 1
   │
   ▼
genera B1 + B2
   │
   ▼
Modelo 2
   │
   ▼
REAL
   │
   ▼
Modelo 3
   │
   ▼
DENIED
   │
   ▼
B1 y B2 vacíos
   │
   ▼
detection_enabled.set()
```

## Usuario autorizado

```text
Modelo 1
   │
   ▼
Modelo 2
   │
   ▼
Modelo 3
   │
   ▼
AUTHORIZED
   │
   ▼
accionar GPIO
   │
   ▼
esperar RISING
   │
   ▼
WAIT_GATE_CLOSE
   │
   ▼
esperar FALLING
   │
   ▼
detection_enabled.set()
```

---

# 23. Hilos iniciales del MVP

La primera implementación podrá disponer de:

```text
Main Thread
    Inicialización y supervisión general.

GPIO Thread
    Espera eventos físicos del final de carrera.

Pipeline Manager Thread
    Gestiona el estado global del pipeline.

Model1 Thread
    Detección facial.

Model2 Thread
    Antispoofing.

Model3 Thread
    Reconocimiento.

Telemetry Thread
    Opcional inicialmente.
```

Los hilos que no tengan trabajo permanecerán bloqueados mediante `Event.wait()` o mediante la espera de eventos GPIO, evitando polling activo.

---

# 24. División propuesta del software

```text
smartgate/
│
├── main.py
│
├── config/
│   └── config.yaml
│
├── core/
│   ├── pipeline_manager.py
│   ├── states.py
│   ├── synchronization.py
│   └── buffers.py
│
├── gpio/
│   ├── gpio_manager.py
│   └── gate_sensor.py
│
├── detection/
│   ├── worker.py
│   └── inference.py
│
├── antispoof/
│   ├── worker.py
│   └── inference.py
│
├── recognition/
│   ├── worker.py
│   ├── inference.py
│   └── repository.py
│
├── gate/
│   └── controller.py
│
├── telemetry/
│   ├── worker.py
│   └── storage.py
│
└── data/
    ├── embeddings.npz
    └── smartgate.db
```

---

# 25. Responsabilidad de cada bloque

## `main.py`

Es la aplicación principal iniciada automáticamente por `systemd` luego del boot de Raspberry Pi OS.

Inicializa y conecta todos los componentes del sistema.

No ejecuta directamente la lógica de los modelos.

## `core/pipeline_manager.py`

Mantiene la FSM global del pipeline y gestiona transiciones como:

```text
IDLE
PROCESSING
WAIT_GATE_OPEN
WAIT_GATE_CLOSE
CLEANING
```

Es el único responsable de habilitar nuevamente Modelo 1 mediante:

```text
detection_enabled.set()
```

## `core/states.py`

Define los estados globales y resultados utilizados entre módulos.

## `core/synchronization.py`

Contiene:

```text
Events
Locks
estado compartido
```

## `core/buffers.py`

Define Buffer 1 y Buffer 2, así como sus operaciones de escritura, lectura, vaciado y protección.

## `gpio/`

Configura los GPIO y espera eventos de flanco.

No ejecuta lógica ML.

## `detection/worker.py`

Espera `detection_enabled`, ejecuta Modelo 1 y genera ambos buffers.

## `detection/inference.py`

Implementa exclusivamente la inferencia del detector.

## `antispoof/worker.py`

Espera `buffer1_ready`, consume Buffer 1 y ejecuta antispoofing.

## `antispoof/inference.py`

Contiene el modelo de antispoofing.

## `recognition/worker.py`

Espera `recognition_ready`, consume Buffer 2 y ejecuta reconocimiento.

## `recognition/inference.py`

Genera embeddings.

## `recognition/repository.py`

Gestiona embeddings conocidos y comparación contra usuarios autorizados.

## `gate/controller.py`

Gestiona la salida física de accionamiento del portón.

Ante una autorización válida llevará el GPIO correspondiente a `HIGH` durante un período fijo y posteriormente lo devolverá a `LOW`.

## `telemetry/`

Recibirá eventos y métricas sin bloquear el pipeline principal.

---

# 26. Reglas fundamentales de implementación

1. Solamente puede existir una muestra activa dentro del pipeline.

2. Modelo 1 queda bloqueado inmediatamente después de aceptar un candidato.

3. El `Pipeline Manager` es el único responsable de volver a habilitar Modelo 1.

4. Cada modelo consume el buffer correspondiente antes de regresar a `IDLE`.

5. Modelo 2 consume Buffer 1.

6. Modelo 3 consume Buffer 2.

7. Si antispoofing rechaza la muestra, Buffer 2 debe ser descartado explícitamente.

8. Si reconocimiento finaliza normalmente, ambos buffers deberán encontrarse vacíos.

9. No se realizará una limpieza global después de cada usuario si el flujo normal ya dejó los recursos en estado conocido.

10. La limpieza global se reserva principalmente para interrupciones asíncronas, errores, shutdown o estados inesperados.

11. Los eventos `modelX_idle` permiten al gestor esperar un punto seguro antes de limpiar recursos.

12. Un `RISING EDGE` esperado después de una autorización solamente lleva al sistema a `WAIT_GATE_CLOSE`.

13. Un `RISING EDGE` inesperado provoca bloqueo de detección, espera de modelos `IDLE` y normalización del pipeline.

14. Un `FALLING EDGE` esperado rearma directamente la detección si el pipeline ya se encuentra limpio.

15. Los hilos bloqueados no deberán realizar polling activo.

16. Las señales de sincronización deberán regresar a su estado de espera al finalizar cada etapa.

17. El sistema deberá poder alcanzar siempre un estado global conocido.

---

# 27. Estado global de referencia

## Búsqueda de usuario

```text
gate_closed       = SET
detection_enabled = SET

Model1 = IDLE/READY
Model2 = IDLE
Model3 = IDLE

Buffer1 = EMPTY
Buffer2 = EMPTY

buffer1_ready     = CLEAR
recognition_ready = CLEAR
```

## Usuario en procesamiento

```text
gate_closed       = SET
detection_enabled = CLEAR
```

Modelo 1 no puede aceptar otro usuario.

## Espera de apertura

```text
Pipeline Manager = WAIT_GATE_OPEN
detection_enabled = CLEAR

Model1 = IDLE
Model2 = IDLE
Model3 = IDLE

Buffers = EMPTY
```

## Portón abierto

```text
gate_closed       = CLEAR
detection_enabled = CLEAR

Pipeline Manager = WAIT_GATE_CLOSE
```

## Portón cerrado nuevamente

```text
FALLING EDGE
      │
      ▼
gate_closed.set()
      │
      ▼
Pipeline Manager = IDLE
      │
      ▼
detection_enabled.set()
```

El sistema vuelve al estado de búsqueda de usuario.