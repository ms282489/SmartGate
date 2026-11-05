# Funcionamiento sin Internet

SmartGate utiliza Supabase para actualizar personas, fotografías y eventos,
pero no depende de la red para reconocer. La última galería sincronizada se
guarda de forma atómica en `data/galeria_rostros.npz`.

Al iniciar, el worker de reconocimiento carga primero ese archivo. Otro worker
intenta conectarse a Supabase en segundo plano. Una demora, un corte de red o
un error de autenticación no detienen cámara, detección, antispoofing,
reconocimiento ni GPIO.

Mientras la placa esté desconectada:

- las personas que ya estaban habilitadas continúan funcionando;
- altas, bajas y nuevas fotos no se reciben hasta recuperar conexión;
- los eventos de acceso se guardan en `data/eventos_pendientes.jsonl`;
- al volver Internet, la galería y los eventos pendientes se sincronizan.

## Primera sincronización

El modo offline necesita que haya ocurrido al menos una sincronización válida.
Para comprobarlo, con Internet disponible ejecutar:

```bash
PYTHONPATH=app python3 testing/probar_supabase.py
```

Después de iniciar SmartGate y ver `Galería facial actualizada`, comprobar:

```bash
ls -lh data/galeria_rostros.npz
```

## Prueba controlada sin Internet

1. Sincronizar y reconocer una persona habilitada.
2. Desconectar la red de la Raspberry.
3. Reiniciar SmartGate.
4. Verificar que aparece `Galería facial local cargada` y que la persona sigue
   siendo reconocida.
5. Recuperar la red y verificar `Conexión con Supabase recuperada`.

No borre `data/galeria_rostros.npz`: es la copia necesaria para el arranque
sin conexión.
