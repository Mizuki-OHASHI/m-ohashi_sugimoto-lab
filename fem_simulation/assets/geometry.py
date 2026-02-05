import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, PathPatch
from matplotlib.path import Path

fig, ax = plt.subplots()

# --- domain boundary ---
ax.text(2.5, -2.3, "(0) Outside domain", ha="center", va="center")

# semiconductor: 0 < r < 5, -2 < z < -0.5
sem_rect = Rectangle((0, -2), 5, 1.5, facecolor="lightblue", edgecolor="black")
ax.add_patch(sem_rect)
ax.text(2.5, -1.25, "(1) Semiconductor", ha="center", va="center")

# oxide: 0 < r < 5, -0.5 < z < 0
ox_rect = Rectangle((0, -0.5), 5, 0.5, facecolor="lightgreen", edgecolor="black")
ax.add_patch(ox_rect)
ax.text(2.5, -0.25, "(2) Oxide", ha="center", va="center")

# vacuum: 0 < r < 5, 0 < z < 2
vac_rect = Rectangle((0, 0), 5, 2, facecolor="lightyellow", edgecolor="black")
ax.add_patch(vac_rect)
ax.text(2.5, 1.0, "(3) Vacuum", ha="center", va="center")

# --- tip geometry ---
# (0, 0.5) arc (半径=0.5, 中心角=75deg) -- (2, 1) -- (0, 2) -- cycle
arc_radius = 0.5
arc_center = (0, 0.5 + arc_radius)  # (0, 1.0)
arc_angle_deg = 75
theta_start = -90  # 開始角（下方向）
theta_end = theta_start + arc_angle_deg  # 終了角
theta = np.linspace(np.radians(theta_start), np.radians(theta_end), 50)
arc_points = [
    (arc_center[0] + arc_radius * np.cos(t), arc_center[1] + arc_radius * np.sin(t))
    for t in theta
]
vertices = [*arc_points, (0.8, 2), (0, 2)]
codes = [Path.MOVETO] + [Path.LINETO] * (len(vertices) - 1)
tip_path = Path(vertices, codes)
tip_patch = PathPatch(tip_path, facecolor="white", edgecolor="black")
ax.add_patch(tip_patch)
ax.text(0.3, 1.3, "Tip", ha="center", va="center")


# --- points ---
points = {
    "ax1": (0, -2),
    "ax2": (0, -0.5),
    "ax3": (0, 0),
    "far1": (5, -2),
    "far2": (5, -0.5),
    "far3": (5, 0),
    "far4": (5, 2),
    "tip_arc[0]": (0, 0.5),
    "tip_arc[-1]": arc_points[-1],
    "tip_edge": (0.8, 2),
}
for name, (x, y) in points.items():
    ax.plot(x, y, "ro")
    ax.text(x + 0.1, y - 0.1, name, va="top")


# --- plot settings ---
ax.set_xlim(-0.5, 5.5)
ax.set_ylim(-2.5, 2.5)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig("geometry.png", dpi=300)
