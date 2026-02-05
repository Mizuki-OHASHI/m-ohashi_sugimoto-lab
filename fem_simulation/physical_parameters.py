from logging import getLogger
from dataclasses import dataclass, asdict, field
import numpy as np
import scipy.constants as const
from scipy.optimize import brentq

from fermi_dirac_integral import F_half_aymerich_humet_np

logger = getLogger(__name__)


@dataclass
class PhysicalParameters:
    T: float = 300.0  # temperature [K]

    Nd: float = 1e22  # donor concentration [m^-3]
    Na: float = 0.0  # acceptor concentration [m^-3]
    ni: float = 8.2e15  # intrinsic carrier concentration [m^-3]

    sigma: float = 1e15  # interface charge density [m^-2]
    # NOTE: バンド曲がりを吸収する界面電荷密度

    mde: float = 0.42 * const.m_e  # effective mass of electrons [kg]
    mdh: float = 1.0 * const.m_e  # effective mass of holes [kg]

    gc: int = 3  # conduction band degeneracy
    gv: int = 1  # valence band degeneracy

    epsilon_sem: float = 9.7  # relative permittivity of semiconductor (SiC)
    epsilon_ox: float = 3.9  # relative permittivity of oxide (SiO2)
    epsilon_vac: float = 1.0  # relative permittivity of vacuum

    Eg: float = 3.26  # bandgap energy [eV] (SiC at 300K)
    Ed: list[float] = field(default_factory=lambda: [0.124, 0.066])
    # NOTE: SiC: 0.124 eV for hex, 0.066 eV for cubic
    #   Ikeda, M., Matsunami, H. & Tanaka, T.
    #   Site effect on the impurity levels in 4 H, 6 H, and 1 5 R SiC.
    #   Phys. Rev. B 22, 2842-2854 (1980).
    donor_ratios: list[float] = field(default_factory=lambda: [1.0, 1.88])
    # NOTE: SiC: cub / hex = 1.88

    Ea: list[float] = field(default_factory=list)  # acceptor energy levels [eV]
    acceptor_ratios: list[float] = field(default_factory=list)

    # calculated after initialization
    kT: float = 0.0
    n0: float = 0.0
    p0: float = 0.0
    Nc: float = 0.0
    Nv: float = 0.0
    Ef: float = 0.0

    def __post_init__(self):
        assert len(self.Ed) == len(self.donor_ratios)
        assert len(self.Ea) == len(self.acceptor_ratios)

        self.kT = const.k * self.T / const.e  # [eV]

        self.n0 = (self.Nd + np.sqrt(self.Nd**2 + 4 * self.ni**2)) / 2
        self.p0 = self.ni**2 / self.n0
        self.Nc = (
            self.gc
            * 2
            * (2 * np.pi * self.mde * const.k * self.T / (const.h**2)) ** 1.5
        )
        self.Nv = (
            self.gv
            * 2
            * (2 * np.pi * self.mdh * const.k * self.T / (const.h**2)) ** 1.5
        )
        self.Ef = self.calc_fermi_level()

        logger.info(asdict(self))

    def calc_fermi_level(self) -> float:
        def charge_neutrality_eq(Ef: float):
            p = self.Nv * F_half_aymerich_humet_np((self.Eg - Ef) / self.kT)
            n = self.Nc * F_half_aymerich_humet_np(Ef / self.kT)

            Ndp = 0.0
            sum_ratios_d = sum(self.donor_ratios)
            for Ed, ratio in zip(self.Ed, self.donor_ratios):
                Ndp += (
                    self.Nd
                    * (ratio / sum_ratios_d)
                    / (1 + 2 * np.exp((Ef - Ed) / self.kT))
                )

            Nap = 0.0
            sum_ratios_a = sum(self.acceptor_ratios)
            for Ea, ratio in zip(self.Ea, self.acceptor_ratios):
                Nap += (
                    self.Na
                    * (ratio / sum_ratios_a)
                    / (1 + 4 * np.exp((Ea - Ef) / self.kT))
                )

            # 安定性のため対数を取る
            return np.log(p + Ndp) - np.log(n + Nap)

        Ef_lower = self.kT
        Ef_upper = self.Eg - self.kT
        Ef, r = brentq(charge_neutrality_eq, Ef_lower, Ef_upper, full_output=True)
        if not r.converged:
            logger.error("Fermi level calculation did not converge.")
            logger.error(str(r))
            raise RuntimeError("Fermi level calculation did not converge.")

        return Ef
