# Medición de tiempos de SmartGate

Hay dos formas de medir, que se complementan:

| Herramienta | Qué mide | Cuándo usarla |
|---|---|---|
| `medir_inferencia.py` | El costo puro de cada modelo, ejecutado muchas veces seguidas, sin hilos ni GPIO. | Para comparar placas y justificar la elección de la Raspberry Pi. |
| Medición integrada + `resumen_tiempos.py` | Cada intento real de acceso: cuánto tarda cada etapa, cada traspaso entre hilos y el total hasta aceptar al usuario. | Para documentar la experiencia real del usuario con el sistema completo. |

Todos los comandos se ejecutan desde la carpeta `TercerPrototipo`, con el
entorno virtual activado. Los resultados se guardan en `data/metricas/`, que
no se sube al repositorio.

## 1. Benchmark de los modelos

Con la cámara (una persona debe quedarse frente a ella durante la medición):

```bash
python3 herramientas/medir_inferencia.py --fuente camara --repeticiones 200
```

Con una fotografía que contenga un rostro (no necesita la cámara):

```bash
python3 herramientas/medir_inferencia.py --fuente imagen --imagen foto.jpg --repeticiones 200
```

Opciones:

- `--personas 100`: simula una galería de 100 personas para ver cómo crece la comparación.
- `--deteccion-completa`: mide también YuNet sobre la imagen de 1280x960, para justificar que la detección se haga a 640x480.
- `--hilos 1`: limita OpenCV a un núcleo (útil para comparar con placas de un núcleo).
- `--calentamiento 10`: iteraciones iniciales que no se cuentan (las primeras son más lentas).

La salida muestra, por etapa, la media, la mediana, el percentil 95, el mínimo
y el máximo en milisegundos, y cuántos cuadros por segundo puede analizar
YuNet. También registra la placa, la temperatura de la CPU antes y después, y
si hubo *throttling* (`vcgencmd get_throttled`, `0x0` significa que no). El
archivo `benchmark_<fecha>.md` se puede pegar directamente en el informe.

Conviene detener el servicio antes de medir, para que no compita por la CPU:

```bash
systemctl --user stop smartgate.service
```

## 2. Medición del sistema completo

1. En `config/config.yaml`, activar la medición:

   ```yaml
   metricas:
     habilitadas: true
   ```

2. Reiniciar SmartGate (`systemctl --user restart smartgate.service`) y hacer
   varios intentos: usuarios autorizados, personas no registradas y una foto
   en el celular (spoof). Para probar sin el portón se puede usar
   `gate.modo_solo_camara: true`.

3. Ver el resumen:

   ```bash
   python3 herramientas/resumen_tiempos.py
   python3 herramientas/resumen_tiempos.py --markdown data/metricas/resumen.md
   ```

4. Volver a `habilitadas: false` al terminar.

### Qué se registra

Cada intento queda como una fila en `data/metricas/tiempos_pipeline.csv`:

| Columna | Desde → hasta |
|---|---|
| `preparacion_deteccion_ms` | cuadro entregado por la cámara → comienza YuNet (redimensionado a 640x480) |
| `yunet_ms` | inferencia de YuNet |
| `recorte_y_buffers_ms` | recortes y carga de Buffer 1 y Buffer 2 |
| `traspaso_a_antispoof_ms` | muestras listas → el hilo de antispoofing toma Buffer 1 |
| `preparacion_antispoof_ms`, `minifasnet_ms` | entrada 80x80 e inferencia de MiniFASNetV2 |
| `antispoof_total_ms` | todo el trabajo del hilo de antispoofing |
| `traspaso_a_reconocimiento_ms` | decisión "real" → el hilo de reconocimiento toma Buffer 2 |
| `alineado_ms`, `sface_ms`, `comparacion_galeria_ms` | alineado, embedding de SFace y comparación con la galería |
| `traspaso_a_gestor_ms` | último modelo → el Pipeline Manager recibe el resultado |
| `gestor_ms` | decisión del gestor hasta pedir el LED de resultado |
| `senal_a_pulso_ms` | orden de apertura → la salida GPIO pasa a HIGH |
| `total_hasta_decision_ms` | cuadro capturado → el gestor recibe el resultado |
| `total_hasta_senal_ms` | cuadro capturado → LED verde o rojo |
| `total_hasta_pulso_ms` | cuadro capturado → pulso al portón (sólo autorizados con portón) |

También se guardan el resultado (`autorizado`, `rechazado` o `spoof`), los
puntajes y la cantidad de personas en la galería, pero no el nombre de la
persona. Si un intento termina por error o por una apertura inesperada del
portón, se descarta.

`data/metricas/tiempos_deteccion.csv` guarda cada inferencia de YuNet mientras
el sistema busca rostros, haya o no una persona. Se puede desactivar con
`registrar_cada_cuadro: false`.

### Qué no incluye el total

El total empieza cuando la cámara entrega el cuadro al programa. No incluye:

- la latencia propia del sensor y de libcamera (exposición y transferencia del cuadro);
- la espera hasta que el detector analiza un cuadro: en modo activo analiza
  cada cuadro (20 fps), y tras 5 segundos sin rostros lo hace cada 0,2 s, por
  lo que puede sumar hasta unos 200 ms al primer intento;
- el tiempo que tarda la central en mover el portón después del pulso.

Para documentar la experiencia del usuario, conviene informar el total junto
con estas aclaraciones.
