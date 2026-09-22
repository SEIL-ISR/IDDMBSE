import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import scienceplots

# Use the science and ieee styles
plt.style.use(['science', 'ieee'])


x = np.load("multiagent/x.npy")

# 2. Define the boxes
# Format: (lower_left_x, lower_left_y, width, height)
obs1 = [-1, .7, 2.25, .6]  # Corners (-1,2) to (0,3)
obs2 = [1.75, .7, 2, .6]   # Corners (2,1) to (3,2)

# boxes = [
#     [-.15, 1.85, .3, .3],
#     [1.35, 1.85, .3, .3],
#     [2.85, 1.85, .3, .3]
# ]

boxes = [
    [-.1, 1.9, .2, .2],
    [1.4, 1.9, .2, .2],
    [2.9, 1.9, .2, .2]
]


fig, ax = plt.subplots(figsize=(6, 4))

for i, box in enumerate([obs1, obs2]):
    rect = patches.Rectangle((box[0], box[1]), box[2], box[3], 
                             edgecolor="black", linewidth=1, facecolor='gray', alpha=0.4, label='Obstacles')
    ax.add_patch(rect)
    # Calculate center: (x + width/2, y + height/2)
    center_x = box[0] + box[2] / 2
    center_y = box[1] + box[3] / 2

    if i == 0:
        ax.text(center_x+.37, center_y, rf"$O_1$", 
                ha='center', va='center', 
                fontsize=14, color='black',
                zorder=2) # Ensures text is above the patch
    if i == 1:
        ax.text(center_x-.22, center_y, rf"$O_2$", 
                ha='center', va='center', 
                fontsize=14, color='black',
                zorder=2) # Ensures text is above the patch

A = ["A", "B", "C"]
for i, box in enumerate(boxes):
    rect = patches.Rectangle((box[0], box[1]), box[2], box[3], 
                             facecolor='darkorange', alpha=0.25, label='Goal Regions')
    ax.add_patch(rect)
    rect = patches.Rectangle((box[0]-.05, box[1]-.05), box[2]+.1, box[3]+.1, 
                             facecolor='darkorange', alpha=0.25, label='Obstacles')
    ax.add_patch(rect)
    # Calculate center: (x + width/2, y + height/2)
    center_x = box[0] + box[2] / 2
    center_y = box[1] + box[3] / 2
    ax.text(center_x, center_y, rf"${A[i]}$", 
                ha='center', va='center', 
                fontsize=14, color='black',
                zorder=2) # Ensures text is above the patch


ax.plot(x[:-1, 0], x[:-1, 2], color="#2e5f7f", linestyle='--', marker='s', fillstyle='none', markersize=4, markevery=1, linewidth=1.2)
ax.plot(x[:-1, 4], x[:-1, 6], color="#da364b", linestyle='--', marker='s', fillstyle='none', markersize=4, markevery=1, linewidth=1.2)
ax.plot(x[:-1, 8], x[:-1, 10], color="#248c2f", linestyle='--', marker='s', fillstyle='none', markersize=4, markevery=1, linewidth=1.2)
# ax.plot(x[:, 6], x[:, 7], linestyle='--', marker='s', fillstyle='none', markersize=4, markevery=1, linewidth=1.2)


ax.set_xlim(-.25, 3.25)
ax.set_ylim(-.1, 2.4)
ax.set_xticks(np.linspace(0, 3, 4))  # Removes x-axis ticks
ax.set_yticks(np.linspace(0, 2, 3))
ax.tick_params(axis='x', labelsize=11)
ax.tick_params(axis='y', labelsize=11)

plt.savefig('trajectory_plot_ma.pdf', format='pdf', bbox_inches='tight', dpi=300)