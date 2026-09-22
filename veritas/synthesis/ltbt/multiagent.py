import numpy as np
np.set_printoptions(threshold=np.inf, linewidth=200, precision=2, suppress=True)
import gurobipy as gp
from gurobipy import GRB

from ltbt.ternary import *

import matplotlib.pyplot as plt

def main():
    
    model = gp.Model("test")

    N = 30

    dt = .25

    num_agents = 3

    X = model.addMVar(
        shape=(N, 2*num_agents), # x and y position
        lb=-5,
        ub=5,
        vtype=GRB.CONTINUOUS
    )
    U = model.addMVar(
        shape=(N-1, 2*num_agents), # x and y velocity
        lb=-1,
        ub=1,
        vtype=GRB.CONTINUOUS
    )

    # evenly spaced
    # X0 = np.array([0, 0, 1, 0, 2, 0, 3, 0])
    # X1 = np.array([2, 3, 0, 3, 3, 3, 1, 3]) # np.array([0, 1, 1, 1, 2, 1])
    # X2 = np.array([1, 0, 2, 0, 3, 0, 0, 0])
    X0 = np.array([0, 0, 1.5, 0, 3, 0])
    X1 = np.array([3, 2, 0, 2, 1.5, 2]) # np.array([0, 1, 1, 1, 2, 1])
    X2 = np.array([1.5, 0, 3, 0, 0, 0])
    X2 = np.array([1.5, 2, 3, 2, 0, 2])
    model.addConstr(
        X[0] == X0   
    )

    # dynamical constraints (1st order)
    for i in range(N-1):
        model.addConstr(
            X[i+1] == X[i] + dt*U[i]   
        )

    
    # now what shall the specifications be?

    safe_distance = 0.3
    # pairs = [
    #     (0, 2, 1, 3), (0, 4, 1, 5), (0, 6, 1, 7), # Agent 1 vs others
    #     (2, 4, 3, 5), (2, 6, 3, 7),               # Agent 2 vs others
    #     (4, 6, 5, 7)                              # Agent 3 vs Agent 4
    # ]
    # Agent 1: (0,1), Agent 2: (2,3), Agent 3: (4,5)
    pairs = [
        (0, 2, 1, 3), # A1 vs A2
        (0, 4, 1, 5), # A1 vs A3
        (2, 4, 3, 5)  # A2 vs A3
    ]
    for i in range(N):
        for pair in pairs:
            z = model.addMVar(
                shape=(4,),
                lb=0,
                ub=1,
                vtype=GRB.BINARY   
            )
            x1,x2,y1,y2 = pair
            model.addGenConstrIndicator(z[0], 1, X[i,x1] - X[i,x2] >=  safe_distance)
            model.addGenConstrIndicator(z[1], 1, X[i,x1] - X[i,x2] <= -safe_distance)
            model.addGenConstrIndicator(z[2], 1, X[i,y1] - X[i,y2] >=  safe_distance)
            model.addGenConstrIndicator(z[3], 1, X[i,y1] - X[i,y2] <= -safe_distance)

            model.addConstr(
                z.sum() >= 1
            )

    # obstacles
    for i in range(N):
        for j in range(0, 2*num_agents, 2):
            z1 = model.addMVar(
                shape=(3,),
                lb=0,
                ub=1,
                vtype=GRB.BINARY
            )
            z2 = model.addMVar(
                shape=(3,),
                lb=0,
                ub=1,
                vtype=GRB.BINARY
            )
            # obs 1
            model.addGenConstrIndicator(
                z1[0], 1, X[i,j] >= 1.4
            )
            model.addGenConstrIndicator(
                z1[1], 1, X[i,j+1] <= .5
            )
            model.addGenConstrIndicator(
                z1[2], 1, X[i,j+1] >= 1.5
            )
            model.addConstr(
                z1.sum() >= 1   
            )
            # obs2
            model.addGenConstrIndicator(
                z2[0], 1, X[i,j] <= 1.6
            )
            model.addGenConstrIndicator(
                z2[1], 1, X[i,j+1] <= .5
            )
            model.addGenConstrIndicator(
                z2[2], 1, X[i,j+1] >= 1.5
            )
            model.addConstr(
                z2.sum() >= 1   
            )
        
        
    x_min = X1-0.1
    x_max = X1+0.1
    mu1 = BoxConstraint(model, X, x_min, x_max)
    x_min = X2-0.1
    x_max = X2+0.1
    mu2 = BoxConstraint(model, X, x_min, x_max)
    phi1 = Eventually(model, mu1, 0, N)
    phi2 = Eventually(model, mu2, 0, N)
    phi = Sequence(model, phi1, phi2, top_level=True)
    # phi.enforce(model, 0)

    model.setObjective(sum(U[i]@U[i] for i in range(N-1)), GRB.MINIMIZE)

    # Spend more time on heuristics to find a feasible solution quickly
    # model.setParam('Heuristics', 0.5) 

    # Focus on finding the global optimum vs. moving the bound
    # 1 = Feasibility, 2 = Optimality, 3 = Bound
    # model.setParam('MIPFocus', 1) 

    # Use multiple cores
    model.setParam('Threads', 0) # 0 uses all available cores

    model.optimize()

    
    t = np.linspace(0, N*dt, N)
    x = X.X
    u = U.X
    z = phi.Z.X

    matrix = np.zeros((N, N))

    # 3. Get the indices for the upper triangle (including the diagonal)
    iu = np.triu_indices(N)

    # 4. Fill the matrix
    matrix[iu] = z

    np.save("multiagent/z.npy", matrix)

    np.save("multiagent/x.npy", x)
    np.save("multiagent/u.npy", u)
    



if __name__ == "__main__":
    main()