"""
Usage
-----
python main.py [config_path] [log_path]
"""

import sys
from dataclasses import asdict
from logging import basicConfig, INFO, getLogger
from pathlib import Path
import toml

from load_config import load_config
from physical_parameters import PhysicalParameters
from geometry import GeometricParameters, create_mesh
from fem import SimulationParameters, run_fem


logger = getLogger(__name__)


def main(config_path: str):
    logger.info(f"Loading configuration from {config_path}")
    conf = load_config(config_path)
    phys = PhysicalParameters(**conf.physical_parameters)
    geom = GeometricParameters(**conf.geometric_parameters)
    siml = SimulationParameters(**conf.simulation_parameters)
    mesh = create_mesh(geom)

    # 設定とパラメータを保存
    out_dir = Path(conf.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # config.toml: 入力設定をコピー
    import shutil

    shutil.copy(config_path, out_dir / "config.toml")
    logger.info(f"Configuration copied to {out_dir / 'config.toml'}")

    # params.toml: 計算されたパラメータを含む完全な状態
    params_path = out_dir / "params.toml"
    with open(params_path, "w") as f:
        toml.dump(
            {
                "physical_parameters": asdict(phys),
                "geometric_parameters": asdict(geom),
                "simulation_parameters": asdict(siml),
            },
            f,
        )
    logger.info(f"Parameters saved to {params_path}")

    logger.info("Starting FEM simulation")
    run_fem(mesh, phys, geom, siml, out_dir)
    logger.info("FEM simulation completed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.toml"
    if len(sys.argv) > 2:
        log_path = sys.argv[2]
    else:
        log_path = None
    if log_path is not None:
        basicConfig(
            level=INFO,
            format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
            filename=log_path,
            filemode="w",
            force=True,
        )
    else:
        basicConfig(
            level=INFO,
            format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
            force=True,
        )
    main(config_path=config_path)
