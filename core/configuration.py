"""Lectura y validacion de la configuracion de SmartGate."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Frozen true quiere decir que estos valores no van a ser modificados posteriormente
@dataclass(frozen=True)
class CameraConfig:
    """Valores necesarios para abrir y configurar la camara."""

    index: int
    width: int
    height: int


@dataclass(frozen=True)
class ThresholdConfig:
    """Puntuaciones minimas utilizadas por los tres modelos."""

    detection: float
    antispoof: float
    recognition: float


@dataclass(frozen=True)
class SmartGateConfig:
    """Configuracion completa que recibiran los componentes del sistema."""

    camera: CameraConfig
    thresholds: ThresholdConfig


def _require_section(data: Any, name: str) -> dict[str, Any]:
    """Obtiene una seccion obligatoria del YAML y comprueba que sea un mapa."""
    if not isinstance(data, dict):
        raise ValueError("La raiz de config.yaml debe contener secciones")

    section = data.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"Falta la seccion obligatoria '{name}'")
    return section


def _require_integer(section: dict[str, Any], name: str, minimum: int) -> int:
    """Lee un numero entero y comprueba su valor minimo permitido."""
    value = section.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"'{name}' debe ser un numero entero")
    if value < minimum:
        raise ValueError(f"'{name}' debe ser mayor o igual que {minimum}")
    return value


def _require_score(section: dict[str, Any], name: str) -> float:
    """Lee una puntuacion y comprueba que se encuentre entre cero y uno."""
    value = section.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"'{name}' debe ser un numero")

    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"'{name}' debe estar entre 0 y 1")
    return score


def load_config(path: Path) -> SmartGateConfig:
    """Lee config.yaml, valida sus valores y devuelve objetos inmutables."""
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Falta PyYAML. Instala las dependencias con "
            "'python -m pip install -r requirements.txt'."
        ) from error

    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo de configuracion: {path}")

    # safe_load interpreta los datos del YAML sin permitir que el archivo
    # ejecute codigo Python.
    with path.open("r", encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file)

    camera_data = _require_section(raw_config, "camera")
    threshold_data = _require_section(raw_config, "thresholds")

    camera = CameraConfig(
        index=_require_integer(camera_data, "index", minimum=0),
        width=_require_integer(camera_data, "width", minimum=1),
        height=_require_integer(camera_data, "height", minimum=1),
    )
    thresholds = ThresholdConfig(
        detection=_require_score(threshold_data, "detection"),
        antispoof=_require_score(threshold_data, "antispoof"),
        recognition=_require_score(threshold_data, "recognition"),
    )

    return SmartGateConfig(camera=camera, thresholds=thresholds)
