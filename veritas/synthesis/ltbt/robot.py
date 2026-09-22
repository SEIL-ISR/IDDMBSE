import numpy as np
np.set_printoptions(threshold=np.inf, linewidth=200, precision=2, suppress=True)
import gurobipy as gp
from gurobipy import GRB

from ltbt.ternary import *

import matplotlib.pyplot as plt


def main():
    model = gp.Model("test")

    N = 15

    X = model.addMVar(
        shape=(N, 4),
        lb=-GRB.INFINITY,
        ub=GRB.INFINITY,
        vtype=GRB.CONTINUOUS
    )
    U = model.addMVar(
        shape=(N-1,2),
        lb=-5,
        ub=5,
        vtype=GRB.CONTINUOUS
    )

    dt = 1
    A = np.array([
        [1, dt, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, dt],
        [0, 0, 0, 1]  
    ])
    B = np.array([
        [dt**2/2, 0],
        [dt, 0],
        [0, dt**2/2],
        [0, dt]
    ])

    # set to TRUE or FALSE
    Batt = Constant(model, N, FALSE)

    # dynamical constraints
    for i in range(N-1):
        model.addConstr(
            X[i+1] == A@X[i] + B@U[i]
        )

    # initial value
    X0 = np.array([0., 0., 0., 0.])
    model.addConstr(
        X[0] == X0   
    )



    ax1 = np.array([1, 0, 0, 0])
    ax2 = np.array([0, 0, 1, 0])

    # a^Tx >= b

    # box 1: -1<=x1<=0 ^ 2<=x2<=3
    x_min = [-.75, None, 2.25, None]
    x_max = [-.25, None, 2.75, None]

    # uncertainty threshold
    delta = None
    
    box1 = BoxConstraint(model, X, x_min, x_max, delta)


    # box 2: 2<=x1<=3 ^ 1<=x2<=2 
    x_min = [2.25, None, 1.25, None]
    x_max = [2.75, None, 1.75, None]

    box2 = BoxConstraint(model, X, x_min, x_max, delta)

    # box 3: -.5<=x1<=.5 ^ -.5<=x2<=.5
    x_min = [-.25, None, -.25, None]
    x_max = [.25, None, .25, None]

    box3 = BoxConstraint(model, X, x_min, x_max, delta)

    ebox1 = Eventually(model, box1, 0, N)
    ebox2 = Eventually(model, box2, 0, N)
    ebox3 = Eventually(model, box3, 0, N)

    sub1 = Selector(model, Batt, ebox3)
    sub2 = Sequence(model, sub1, ebox2)

    phi = Sequence(model, ebox1, sub2)

    phi.enforce(model, 0, any=True)

    model.update()

    print(f"\nvars: {model.NumBinVars+model.NumIntVars+model.NumVars}")
    print(f"\nconstraints: {model.NumConstrs+model.NumGenConstrs+model.NumQConstrs}\n")

    model.setObjective(sum(U[i]@U[i] for i in range(N-1)), GRB.MINIMIZE)
    model.optimize()

    t = np.linspace(0, N*dt, N)
    x = X.X
    u = U.X
    z = phi.Z.X

    np.save("robot/x.npy", x)
    np.save("robot/u.npy", u)

    plt.plot(x[:, 0], x[:, 2])
    plt.savefig("test.png")

    matrix = np.zeros((N, N))

    # 3. Get the indices for the upper triangle (including the diagonal)
    iu = np.triu_indices(N)

    # 4. Fill the matrix
    matrix[iu] = z

    np.save("robot/z.npy", matrix)

    print(matrix)
    print()
    print(x)


if __name__ == "__main__":
    main()
