from pathlib import Path
from logging import getLogger
from dataclasses import dataclass, asdict
import ngsolve as ng
import numpy as np
import scipy.constants as const

from fermi_dirac_integral import F_half_aymerich_humet_ng
from physical_parameters import PhysicalParameters
from geometry import GeometricParameters


logger = getLogger(__name__)


@dataclass
class SimulationParameters:
    Vtip_list: list[float]  # list of tip voltages [V]

    # Newton solver parameters
    maxit: int = 100
    maxerr: float = 1e-11
    dampfactor: int = 1
    # NOTE: ダンピング係数: 1 -> ダンピングなし, 大きいほどダンピングが強くなる


def run_fem(
    mesh: ng.Mesh,
    phys: PhysicalParameters,
    geom: GeometricParameters,
    siml: SimulationParameters,
    out_dir: Path,
):
    V = ng.H1(mesh, order=1)  # 関数空間
    u = ng.GridFunction(V, name="electrostatic_potential")  # 解 (静電ポテンシャル)

    # ホモトピー変数: 0 -> 初期問題, 1 -> 本来の問題
    hmtp_charge = ng.Parameter(0.0)  # 電荷密度 (非線形項)
    hmtp_sigma = ng.Parameter(0.0)  # 界面電荷密度

    a = _setup_weak_form(mesh, V, phys, geom, hmtp_charge, hmtp_sigma)

    out_dir.mkdir(parents=True, exist_ok=True)
    for i, Vtip in enumerate(siml.Vtip_list):
        logger.info(
            f"Solving for tip voltage Vtip = {Vtip:.2f} V ({i+1}/{len(siml.Vtip_list)})"
        )
        # set boundary conditions (dirichlet)
        u.Set(ng.CoefficientFunction(0.0), definedon=mesh.Boundaries(geom.bc_ground))
        u.Set(
            ng.CoefficientFunction(Vtip / phys.kT),
            definedon=mesh.Boundaries(geom.bc_tip),
        )
        _solve_newton(mesh, geom, siml, a, u, V, hmtp_charge, hmtp_sigma)
        dir_path = out_dir / f"Vtip_{Vtip:.2f}V"
        dir_path.mkdir(parents=True, exist_ok=True)
        _save_potential(mesh, u, phys, geom, dir_path)


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


def _solve_newton(
    mesh: ng.Mesh,
    geom: GeometricParameters,
    siml: SimulationParameters,
    a: ng.BilinearForm,
    u: ng.GridFunction,
    V: ng.H1,
    hmtp_charge: ng.Parameter,
    hmtp_sigma: ng.Parameter,
):
    hmtp_charge.Set(1.0)
    hmtp_sigma.Set(1.0)

    freedofs = V.FreeDofs()
    freedofs &= ~V.GetDofs(mesh.Boundaries(geom.bc_ground))
    freedofs &= ~V.GetDofs(mesh.Boundaries(geom.bc_tip))

    a.Assemble()

    logger.info("starting Newton solver...")
    converged, iter = ng.solvers.Newton(
        a,
        u,
        freedofs,
        maxit=siml.maxit,
        maxerr=siml.maxerr,
        inverse="sparsecholesky",
        dampfactor=siml.dampfactor,
        printing=False,
    )
    if converged >= 0:
        logger.info(f"Newton solver converged in {iter} iterations.")
        return

    # 収束しない場合は homotopy 法で非線形項を徐々に導入
    logger.warning("Newton solver did not converge, using homotopy method...")
    n_hmtp_steps = 10
    for step in range(n_hmtp_steps + 1):
        hmtp_value = step / n_hmtp_steps
        hmtp_charge.Set(hmtp_value)
        hmtp_sigma.Set(hmtp_value)
        converged, iter = ng.solvers.Newton(
            a,
            u,
            freedofs,
            maxit=siml.maxit,
            maxerr=siml.maxerr,
            inverse="sparsecholesky",
            dampfactor=siml.dampfactor,
            printing=False,
        )
        if converged >= 0:
            logger.info(
                f"  homotopy step {step+1}/{n_hmtp_steps} converged in {iter} iterations."
            )
        else:
            logger.error(f"  homotopy step {step+1}/{n_hmtp_steps} did not converge.")
            raise RuntimeError("Newton solver did not converge even with homotopy.")
    logger.info("Newton solver converged with homotopy method.")


def _save_potential(
    mesh: ng.Mesh,
    u: ng.GridFunction,
    phys: PhysicalParameters,
    geom: GeometricParameters,
    dir_path: Path,
    n_points=500,
):
    u_np = u.vec.FV().NumPy()
    potential_dimless_path = dir_path / "potential_dimless.npy"
    np.save(potential_dimless_path, u_np)
    logger.info(
        f"Electrostatic potential (dimensionless) saved to {potential_dimless_path}"
    )

    # save line profiles
    potential_interface_path = dir_path / "potential_interface.txt"
    r_coords = np.linspace(0, geom.l_radius, n_points + 1, endpoint=True)
    interface_coords = np.column_stack((r_coords, np.full_like(r_coords, -geom.l_ox)))
    valid_r_interface, potential_r_interface = _valuate_potential_at_line(
        u, mesh, interface_coords, "horizontal", phys.kT
    )
    np.savetxt(
        potential_interface_path,
        np.column_stack((valid_r_interface, potential_r_interface)),
        header="r[nm],potential[V]",
        comments="",
        delimiter=",",
    )
    logger.info(
        f"Electrostatic potential at interface saved to {potential_interface_path}"
    )

    potential_axis_path = dir_path / "potential_axis.txt"
    z_coords = np.linspace(
        -(geom.l_ox + geom.l_sem), geom.l_sem, n_points + 1, endpoint=True
    )
    axis_coords = np.column_stack((np.full_like(z_coords, 0.0), z_coords))
    valid_z_axis, potential_z_axis = _valuate_potential_at_line(
        u, mesh, axis_coords, "vertical", phys.kT
    )
    np.savetxt(
        potential_axis_path,
        np.column_stack((valid_z_axis, potential_z_axis)),
        header="z[nm],potential[V]",
        comments="",
        delimiter=",",
    )
    logger.info(f"Electrostatic potential at axis saved to {potential_axis_path}")


def _valuate_potential_at_line(
    u: ng.GridFunction, msh: ng.Mesh, coords: np.ndarray, axis: str, Vc: float
):
    potential = []
    valid = []

    for coord in coords:
        try:
            if axis == "vertical":
                val = u(msh(0.0, coord)) * Vc  # type: ignore
            else:  # horizontal
                val = u(msh(coord[0], coord[1])) * Vc
            potential.append(val)
            valid.append(coord if axis == "vertical" else coord[0])
        except Exception:
            continue

    return np.array(valid), np.array(potential)
