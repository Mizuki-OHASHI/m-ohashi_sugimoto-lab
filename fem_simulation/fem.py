from logging import getLogger
from dataclasses import dataclass, asdict
import ngsolve as ng
import scipy.constants as const

from fermi_dirac_integral import F_half_aymerich_humet_ng
from physical_parameters import PhysicalParameters
from geometry import GeometricParameters


logger = getLogger(__name__)


@dataclass
class SimulationParameters:
    V_tip_lst: list[float]  # list of tip voltages [V]


def run_fem(
    mesh: ng.Mesh,
    phys: PhysicalParameters,
    geom: GeometricParameters,
    siml: SimulationParameters,
):
    V = ng.H1(mesh, order=1)  # 関数空間
    u = ng.GridFunction(V, name="electrostatic_potential")  # 解 (静電ポテンシャル)

    # ホモトピー変数: 0 -> 初期問題, 1 -> 本来の問題
    hmtp_charge = ng.Parameter(0.0)  # 電荷密度 (非線形項)
    hmtp_sigma = ng.Parameter(0.0)  # 界面電荷密度

    a = _setup_weak_form(mesh, V, phys, geom, hmtp_charge, hmtp_sigma)

    for i, V_tip in enumerate(siml.V_tip_lst):
        # set boundary conditions (dirichlet)
        u.Set(ng.CoefficientFunction(0.0), definedon=mesh.Boundaries(geom.bc_ground))
        u.Set(
            ng.CoefficientFunction(V_tip / phys.kT),
            definedon=mesh.Boundaries(geom.bc_tip),
        )
        _solve_newton()


def _clamp(val, bound):
    return ng.IfPos(val - bound, bound, ng.IfPos(-bound - val, -bound, val))


def _safe_exp(x):
    x_clip = _clamp(x, 40.0)
    return ng.exp(x_clip)


def _setup_weak_form(
    mesh: ng.Mesh,
    V: ng.H1,
    phys: PhysicalParameters,
    geom: GeometricParameters,
    hmtp_charge: ng.Parameter,
    hmtp_sigma: ng.Parameter,
) -> ng.BilinearForm:
    uh, vh = V.TnT()
    c = (const.e * geom.Lc**2) / (const.epsilon_0 * phys.kT)
    u_clip = _clamp(uh, 120.0)

    n = c * phys.Nc * F_half_aymerich_humet_ng((phys.Ef - phys.Eg) / phys.kT + u_clip)
    p = c * phys.Nv * F_half_aymerich_humet_ng((-phys.Ef) / phys.kT - u_clip)

    Ndp = ng.CoefficientFunction(0.0)
    sum_ratios_d = sum(phys.donor_ratios)
    for Ed, ratio in zip(phys.Ed, phys.donor_ratios):
        Ndp += ng.CoefficientFunction(
            phys.Nd
            * (ratio / sum_ratios_d)
            / (1 + 2 * _safe_exp((phys.Ef - Ed) / phys.kT + u_clip))
        )
    Nap = ng.CoefficientFunction(0.0)
    sum_ratios_a = sum(phys.acceptor_ratios)
    for Ea, ratio in zip(phys.Ea, phys.acceptor_ratios):
        Nap += ng.CoefficientFunction(
            phys.Na
            * (ratio / sum_ratios_a)
            / (1 + 4 * _safe_exp((Ea - phys.Ef) / phys.kT - u_clip))
        )

    rho = hmtp_charge * (p - n + Ndp - Nap)
    sigma = hmtp_sigma * phys.sigma * (const.e * geom.Lc) / (const.epsilon_0 * phys.kT)

    epsilon_r = ng.CoefficientFunction(
        [phys.epsilon_sem, phys.epsilon_ox, phys.epsilon_vac]
    )

    # robin boundary condition coeffs
    robin_coeff = 1 / (geom.l_radius * 1e-9 / geom.Lc)
    a = ng.BilinearForm(V)
    a += epsilon_r * ng.grad(uh) * ng.grad(vh) * ng.x * ng.dx
    a += epsilon_r * robin_coeff * uh * vh * ng.x * ng.ds(geom.bc_far)
    a += -rho * vh * ng.x * ng.dx(definedon=mesh.Materials(geom.sem_name))
    a += -sigma * vh * ng.x * ng.ds(geom.bc_intf)

    return a


def _solve_newton(): ...
