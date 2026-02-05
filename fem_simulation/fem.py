from logging import getLogger
from dataclasses import dataclass, asdict
import ngsolve as ng

from fermi_dirac_integral import F_half_aymerich_humet_ng
from physical_parameters import PhysicalParameters


@dataclass
class SimulationParameters: ...


def run_fem(mesh: ng.Mesh, params: PhysicalParameters, siml: SimulationParameters): ...


def _setup_weak_form(): ...


def _solve_homotopy(): ...
