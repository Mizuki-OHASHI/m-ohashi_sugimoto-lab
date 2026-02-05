from logging import getLogger
from dataclasses import dataclass, asdict
import numpy as np
import scipy.constants as const
from netgen.geom2d import SplineGeometry
from ngsolve import Mesh

logger = getLogger(__name__)


@dataclass
class GeometricParameters:
    tip_sample_distance: float  # tip-sample distance [m]

    Lc: float = 1.0 * const.nano  # characteristic length [m]
    # NOTE: 特徴的な長さスケール. 数値計算の安定化のために使用

    # vertical dimensions
    l_vac: float = 200.0 * const.nano  # vacuum thickness [m]
    l_ox: float = 1.0 * const.nano  # oxide thickness [m]
    l_sem: float = 195.0 * const.nano  # semiconductor thickness [m]

    # lateral dimensions
    l_radius: float = 500.0 * const.nano  # radius of the simulation domain [m]

    # tip geometry
    tip_radius: float = 40.0 * const.nano  # tip radius [m]
    tip_slope_deg: float = 15.0  # tip slope [degrees]

    # mesh parameters
    n_tip_arc_points: int = 9
    # NOTE: number of mesh points along the tip arc, must be >= 3 and odd
    #   Netgen では円弧を直接指定できないので, 円弧上に離散点を配置してその間を 3 次のスプライン補間で結ぶ
    mesh_scale: float = 1.0  # mesh scale factor

    # domain index
    out_id = 0
    sem_id = 1
    ox_id = 2
    vac_id = 3
    sem_name = "semiconductor"
    ox_name = "oxide"
    vac_name = "vacuum"

    # boundary conditions
    bc_axis = "axis"
    bc_far = "far-field"
    bc_ground = "ground"
    bc_top = "top"
    bc_surf = "surface"  # Oxide-Vacuum surface
    bc_intf = "interface"  # Oxide-Semiconductor interface
    bc_tip = "tip"  # Tip surface

    def __post_init__(self):
        assert self.n_tip_arc_points >= 3 and self.n_tip_arc_points % 2 == 1
        assert 0.1 <= self.mesh_scale <= 10.0

        logger.info(asdict(self))
        # lines = json.dumps(asdict(self), indent=4).splitlines()
        # for line in lines:
        #     logger.info(line)


def create_mesh(geom: GeometricParameters) -> Mesh:
    # dimensionless parameters
    l_vac = geom.l_vac / geom.Lc
    l_ox = geom.l_ox / geom.Lc
    l_sem = geom.l_sem / geom.Lc
    l_radius = geom.l_radius / geom.Lc
    tip_height = geom.tip_sample_distance / geom.Lc
    tip_radius = geom.tip_radius / geom.Lc
    tip_slope_rad = np.deg2rad(geom.tip_slope_deg)

    g = SplineGeometry()

    # --- points ---
    # NOTE: 点の名前 はfem_simulation/assets/geometry.png を参照

    # axes points
    ax1 = g.AppendPoint(0, -(l_sem + l_ox))
    ax2 = g.AppendPoint(0, -l_ox)
    ax3 = g.AppendPoint(0, 0)

    # far-field points
    far1 = g.AppendPoint(l_radius, -(l_sem + l_ox))
    far2 = g.AppendPoint(l_radius, -l_ox)
    far3 = g.AppendPoint(l_radius, 0)
    far4 = g.AppendPoint(l_radius, l_vac)

    # tip geometry points
    tip_arc_center = tip_radius + tip_height
    theta = np.linspace(
        0, np.pi / 2 - tip_slope_rad, geom.n_tip_arc_points, endpoint=True
    )
    tip_arc_r = tip_radius * np.sin(theta)
    tip_arc_z = tip_arc_center - tip_radius * np.cos(theta)
    tip_arc_points = [
        g.AppendPoint(r, z) for r, z in zip(list(tip_arc_r), list(tip_arc_z))
    ]
    tip_edge_r = tip_arc_r[-1] + (l_vac - tip_arc_z[-1]) * np.tan(tip_slope_rad)
    tip_edge = g.AppendPoint(tip_edge_r, l_vac)

    # --- lines ---
    out_id = geom.out_id
    sem_id = geom.sem_id
    ox_id = geom.ox_id
    vac_id = geom.vac_id

    bc_axis = geom.bc_axis
    bc_far = geom.bc_far
    bc_ground = geom.bc_ground
    bc_top = geom.bc_top
    bc_surf = geom.bc_surf
    bc_intf = geom.bc_intf
    bc_tip = geom.bc_tip

    # axes lines
    g.Append(["line", ax1, ax2], bc=bc_axis, leftdomain=out_id, rightdomain=sem_id)
    g.Append(["line", ax2, ax3], bc=bc_axis, leftdomain=out_id, rightdomain=ox_id)
    g.Append(
        ["line", ax3, tip_arc_points[0]],
        bc=bc_axis,
        leftdomain=out_id,
        rightdomain=vac_id,
    )

    # far-field lines
    g.Append(["line", far1, far2], bc=bc_far, leftdomain=sem_id, rightdomain=out_id)
    g.Append(["line", far2, far3], bc=bc_far, leftdomain=ox_id, rightdomain=out_id)
    g.Append(["line", far3, far4], bc=bc_far, leftdomain=vac_id, rightdomain=out_id)

    # lateral lines
    g.Append(["line", ax1, far1], bc=bc_ground, leftdomain=sem_id, rightdomain=out_id)
    g.Append(["line", ax2, far2], bc=bc_intf, leftdomain=ox_id, rightdomain=sem_id)
    g.Append(["line", ax3, far3], bc=bc_surf, leftdomain=vac_id, rightdomain=ox_id)
    g.Append(["line", tip_edge, far4], bc=bc_top, leftdomain=out_id, rightdomain=vac_id)

    # tip lines
    for i in range(0, geom.n_tip_arc_points - 2, 2):
        g.Append(
            [
                "spline3",
                tip_arc_points[i],
                tip_arc_points[i + 1],
                tip_arc_points[i + 2],
            ],
            bc=bc_tip,
            leftdomain=out_id,
            rightdomain=vac_id,
        )
    assert i + 3 == geom.n_tip_arc_points
    g.Append(
        ["line", tip_arc_points[-1], tip_edge],
        bc=bc_tip,
        leftdomain=out_id,
        rightdomain=vac_id,
    )

    # --- materials ---
    g.SetMaterial(sem_id, geom.sem_name)
    g.SetMaterial(ox_id, geom.ox_name)
    g.SetMaterial(vac_id, geom.vac_name)

    # --- generate mesh ---
    logger.info("Generating mesh...")
    # fine mesh for oxide layer and near-tip region
    g.SetDomainMaxH(ox_id, 2 * geom.mesh_scale)
    ngmesh = g.GenerateMesh(maxh=10 * geom.mesh_scale, grading=0.2)
    mesh = Mesh(ngmesh)
    logger.info(f"Mesh generated with {mesh.ne} elements and {mesh.nv} vertices")
    return mesh
