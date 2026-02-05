from logging import basicConfig, INFO, getLogger
from load_config import load_config

from physical_parameters import PhysicalParameters
from geometry import GeometricParameters, create_mesh
from fem import SimulationParameters, run_fem


logger = getLogger(__name__)


def main(config_path: str):
    conf = load_config(config_path)
    phys = PhysicalParameters(**conf.physical_parameters)
    geom = GeometricParameters(**conf.geometric_parameters)
    siml = SimulationParameters(**conf.simulation_parameters)
    mesh = create_mesh(geom)
    results = run_fem(mesh, phys, geom, siml)


if __name__ == "__main__":
    log_path = None
    if log_path is not None:
        basicConfig(
            level=INFO,
            format="%(asctime)s | %(levelname)s | (%(name)s) %(message)s",
            filename=log_path,
            filemode="w",
            force=True,
        )
    else:
        basicConfig(
            level=INFO,
            format="%(asctime)s | %(levelname)s | (%(name)s) %(message)s",
            force=True,
        )
    main(config_path="config.toml")
