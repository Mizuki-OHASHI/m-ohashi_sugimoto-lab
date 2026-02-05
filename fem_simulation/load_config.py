import toml
from logging import getLogger
from dataclasses import dataclass, asdict

logger = getLogger(__name__)


@dataclass
class FEMConfig:
    physical_parameters: dict
    geometric_parameters: dict
    simulation_parameters: dict
    out_dir: str


def load_config(config_path: str) -> FEMConfig:
    with open(config_path, "r") as f:
        conf_dict = toml.load(f)
    logger.info(f"Configuration loaded from {config_path}")
    return FEMConfig(
        physical_parameters=conf_dict["physical_parameters"],
        geometric_parameters=conf_dict["geometric_parameters"],
        simulation_parameters=conf_dict["simulation_parameters"],
        out_dir=conf_dict["out_dir"],
    )
