import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import scienceplots
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as patches

plt.style.use(['science', 'ieee'])
plt.rcParams["axes.axisbelow"] = False 
N = 20
dt = 0.5
x = np.load("multiagent/x.npy")
t = np.linspace(0, (N-1)*dt, N)

y1 = x[:,2]
y2 = x[:,6]
y3 = x[:,10]

t = t[:15]
y1 = y1[:15]
y2 = y2[:15]
y3 = y3[:15]

fig, ax = plt.subplots(figsize=(6, 3))


# Plotting
ax.plot(t, y1, color="#2e5f7f", linestyle='--', linewidth=1.2, label=r"Agent 1", zorder=0)
ax.plot(t, y2, color="#da364b", linestyle='--', linewidth=1.2, label=r"Agent 2", zorder=0)
ax.plot(t, y3, color="#248c2f", linestyle='--', linewidth=1.2, label=r"Agent 3", zorder=0)


white_fade = LinearSegmentedColormap.from_list('white_fade', [(1, 1, 1, 0), (1, 1, 1, 1)])

plt.imshow(
    [[0, 1],
    [0, 1]],
    cmap=white_fade,
    interpolation = 'bilinear',
    zorder=1,
    origin="lower",
    extent=[2, 7.9, 0, 2.5],
)




# Intersection Logic for y = 1
target_y = 1
ys = [y1, y2, y3]
colors = ["#2e5f7f", "#da364b", "#248c2f"]

for y_series, color in zip(ys, colors):
    # This finds the t-value where y_series == 1 via linear interpolation
    # Note: This assumes y is monotonic (only crosses once)
    t_cross = np.interp(target_y, y_series, t)
    
    # Check if the value was actually reached in your data range
    if y_series.min() <= target_y <= y_series.max():
        # Draw the lines from axes to the point (t_cross, 1)
        ax.axvline(x=t_cross, ymin=0, ymax=target_y/ax.get_ylim()[1]+0.05, color=color, linestyle=':', alpha=0.8)
        ax.axhline(y=target_y, xmin=0, xmax=t_cross/t[-1]+.05, color="gray", linestyle=':', alpha=0.8)
        
        # Add a dot at the intersection
        ax.scatter(t_cross, target_y, color=color, s=10, zorder=5)

ax.text(1, target_y + 0.05, "navigating through\n obstacles", 
        fontsize=11, color="black", ha='center', va='bottom',
        bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=1))

# Formatting
ax.set_xlabel(r"Time (s)", fontsize=11)
ax.set_ylabel(r"$x^2$", fontsize=11)
ax.tick_params(axis='both', labelsize=11)
ax.set_yticks([0, 1, 2])
ax.set_xlim([0, 6.5])
ax.set_ylim([-.1, 2.3])

handles, labels = ax.get_legend_handles_labels()
by_label = dict(zip(labels, handles))
leg = ax.legend(by_label.values(), by_label.keys(), fontsize=11, loc="lower right")

ax.tick_params(axis='both', which='both', zorder=100)
# Set the legend's z-order to a high value (e.g., 100) to bring it to the front
leg.set_zorder(100)


plt.savefig("queue.pdf", format='pdf', bbox_inches='tight', dpi=300)