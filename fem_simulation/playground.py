from logging import DEBUG, basicConfig
from pprint import pprint

from geometry import GeometricParameters, create_mesh
from physical_parameters import PhysicalParameters

basicConfig(
    level=DEBUG,
    format="%(asctime)s | %(levelname)s | (%(name)s) %(message)s",
    force=True,
)

params = PhysicalParameters()
pprint(params)

geom = GeometricParameters(tip_sample_distance=5.0e-9)
pprint(geom)
mesh = create_mesh(geom)
