"""Configuración común del cliente de Supabase para la Raspberry."""

from pathlib import Path


CARPETA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_ENV = CARPETA_PROYECTO / "app" / ".env"


def cargar_credenciales_supabase():
    """Lee y valida las credenciales sin mostrarlas en los mensajes."""

    from dotenv import dotenv_values

    credenciales = dotenv_values(RUTA_ENV)
    variables = (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_DEVICE_EMAIL",
        "SUPABASE_DEVICE_PASSWORD",
    )
    faltantes = [
        nombre
        for nombre in variables
        if not credenciales.get(nombre)
    ]

    if faltantes:
        raise RuntimeError(
            "Faltan variables en app/.env: "
            + ", ".join(faltantes)
        )

    url = str(credenciales["SUPABASE_URL"]).strip().rstrip("/")
    if not url.startswith(("https://", "http://")):
        raise RuntimeError(
            "SUPABASE_URL debe comenzar con https:// o http://"
        )

    credenciales["SUPABASE_URL"] = url
    return credenciales


def crear_cliente_supabase(config=None):
    """Crea una sesión autenticada con tiempos de espera acotados."""

    from supabase import create_client

    try:
        # Ruta pública utilizada por las versiones actuales.
        from supabase import ClientOptions
    except ImportError:  # Compatibilidad con versiones 2.x anteriores.
        from supabase.client import ClientOptions

    credenciales = cargar_credenciales_supabase()
    config_supabase = (config or {}).get("supabase", {})
    timeout_postgrest = float(
        config_supabase.get("postgrest_timeout_seconds", 10)
    )
    timeout_storage = float(
        config_supabase.get("storage_timeout_seconds", 15)
    )

    opciones = ClientOptions(
        postgrest_client_timeout=timeout_postgrest,
        storage_client_timeout=timeout_storage,
        schema="public",
    )
    cliente = create_client(
        credenciales["SUPABASE_URL"],
        credenciales["SUPABASE_PUBLISHABLE_KEY"],
        options=opciones,
    )
    respuesta = cliente.auth.sign_in_with_password(
        {
            "email": credenciales["SUPABASE_DEVICE_EMAIL"],
            "password": credenciales["SUPABASE_DEVICE_PASSWORD"],
        }
    )

    if not getattr(respuesta, "session", None):
        raise RuntimeError(
            "Supabase no devolvió una sesión para el usuario del dispositivo"
        )

    return cliente


def describir_error_supabase(error):
    """Devuelve un diagnóstico breve sin imprimir secretos."""

    texto = " ".join(str(error).split())
    if len(texto) > 300:
        texto = texto[:297] + "..."

    return f"{type(error).__name__}: {texto}"
