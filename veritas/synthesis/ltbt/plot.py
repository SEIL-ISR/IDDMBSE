import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import scienceplots

# Use the science and ieee styles
plt.style.use(['science', 'ieee'])

# 1. Generate a dummy trajectory X for demonstration
# In your real code, replace this with your Gurobi solution data

# X_F = np.load("robot/false/x.npy")
# X_T = np.load("robot/true/x.npy")

X_F = np.load("robot/false/x.npy")
X_T = np.load("robot/true/x.npy")

# 2. Define the boxes
# Format: (lower_left_x, lower_left_y, width, height)
box1 = [-1, 2, 1, 1]  # Corners (-1,2) to (0,3)
box2 = [2, 1, 1, 1]   # Corners (2,1) to (3,2)
box3 = [-.5, -.5, 1, 1]

fig, ax = plt.subplots(figsize=(5, 4))

# 3. Add shaded boxes
# 'alpha' controls the lightness, 'fc' is facecolor, 'ec' is edgecolor
A = ["A", "B", "C"]
for i, box in enumerate([box1, box2, box3]):
    rect = patches.Rectangle((box[0], box[1]), box[2], box[3], 
                             linewidth=0, facecolor='darkorange', alpha=0.25, label='Goal Regions')
    ax.add_patch(rect)
    rect = patches.Rectangle((box[0]+.25, box[1]+.25), box[2]-.5, box[3]-.5, 
                             linewidth=0, facecolor='darkorange', alpha=0.25, label='Goal Regions')
    ax.add_patch(rect)
    # Calculate center: (x + width/2, y + height/2)
    center_x = box[0] + box[2] / 2
    center_y = box[1] + box[3] / 2
    
    # Add the text label
    if i == 2:
        ax.text(center_x-.37, center_y-.37, rf"${A[i]}$", 
                ha='center', va='center', 
                fontsize=14, color='black',
                zorder=2) # Ensures text is above the patch
    else:
        ax.text(center_x, center_y, rf"${A[i]}$", 
                ha='center', va='center', 
                fontsize=14, color='black',
                zorder=2) # Ensures text is above the patch

# 4. Plot the trajectory
ax.plot(X_T[:-1, 0], X_T[:-1, 2], 
        label=r"$\text{Batt}\geq80\%$", 
        linestyle='--', 
        marker='s',
        fillstyle='none', 
        markersize=4,      # Adjust based on your N (horizon)
        markevery=1,       # Set to >1 if the points are too crowded
        linewidth=1.2, 
        color="#248c2f")

ax.plot(X_F[:-1, 0], X_F[:-1, 2], 
        label=r"$\text{Batt}<80\%$", 
        linestyle='--', 
        marker='o',
        fillstyle='none',
        markersize=4,      # Adjust based on your N (horizon)
        markevery=1,       # Set to >1 if the points are too crowded
        linewidth=1.2, 
        color="#da364b")

# 5. Formatting labels (SciencePlots + IEEE style handles Times New Roman)
#ax.set_xlabel(r"$x^1$", fontsize=12)
#ax.set_ylabel(r"$x^2$", fontsize=12)
# ax.set_title('Robot Trajectory')

# Clean up legend (remove duplicate 'Constraints' labels)
handles, labels = ax.get_legend_handles_labels()
by_label = dict(zip(labels, handles))
ax.legend(by_label.values(), by_label.keys(), fontsize=10, loc="lower right")

# Force axis limits to see the boxes clearly
ax.set_xlim(-1, 3)
ax.set_ylim(-.5, 3)
ax.set_xticks(np.linspace(-1, 3, 5))
ax.set_yticks(np.linspace(0, 3, 4))
ax.tick_params(axis='x', labelsize=10)
ax.tick_params(axis='y', labelsize=10)


plt.savefig('trajectory_plot_tern_ticks.pdf', format='pdf', bbox_inches='tight', dpi=300)