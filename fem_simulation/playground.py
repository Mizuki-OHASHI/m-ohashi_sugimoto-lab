# %%
from pprint import pprint

# %%
from logging import basicConfig, DEBUG

basicConfig(
    level=DEBUG,
    format="%(asctime)s | %(levelname)s | (%(name)s) %(message)s",
    force=True,
)

# %%
from physical_parameters import PhysicalParameters

params = PhysicalParameters()
pprint(params)

# %%
from geometry import GeometricParameters, create_mesh

geom = GeometricParameters(tip_sample_distance=5.0e-9)
pprint(geom)
mesh = create_mesh(geom)

# %%
