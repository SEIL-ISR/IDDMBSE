import numpy as np
import gurobipy as gp

from gurobipy import GRB

import matplotlib.pyplot as plt

from typing import Literal

eps = 1e-6
M = 1e3

TRUE:    int =  1
UNKNOWN: int =  0
FALSE:   int = -1

K3 = Literal[FALSE, UNKNOWN, TRUE]


class Node:
    """Abstract node class for semantics tree.
    
    ...
    """

    def __init__(self) -> None:
        # Must be overloaded

        self.N: int
        self.Z: gp.MVar

        pass
    
    def __str__(self) -> str:
        # Must be overloaded
        pass
    
    def enforce(self, model, t):
        # Must be overloaded
        pass
    
    def __getitem__(self, key) -> gp.Var:
        # Must be overloaded
        pass
    
class LinearPredicate(Node):
    """Linear predicate of the form a^Tx >= b.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        X: gp.MVar,
        a: np.array,
        b: float
    ) -> None:
        """

        """

        assert a.shape[0] == X.shape[1]

        self.a = a
        self.b = b

        self.N = X.shape[0]

        self.Z = model.addMVar(
            shape=(self.N,),
            lb=FALSE, # is this readable?
            ub=TRUE,  # or is this stupid
            vtype=GRB.INTEGER
        )
        # binaries
        U = model.addMVar(
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER   
        )

        # z=1  => ax>=b
        # z=-1 => ax<b

        for i in range(self.N):
            # positive
            model.addGenConstrIndicator(
                U[i], 1, a@X[i] >= b   
            )
            # negative
            model.addGenConstrIndicator(
                U[i], 0, a@X[i] <= b - eps
            )
            # trit
            model.addConstr(
                self.Z[i] == 2*U[i] - 1   
            )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        model.addConstr(
            self.Z[t] == TRUE   
        )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """

        # only one temporal dimension
        i, j = key
        
        return self.Z[i]
    
class TernaryPredicate(Node):
    """Ternary predicate with uncertainty band.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        X: gp.MVar,
        a: np.array,
        b: float,
        delta: float
    ) -> None:
        
        assert a.shape[0] == X.shape[1]

        self.a = a
        self.b = b
        self.delta = delta

        self.N = X.shape[0]

        self.Z = model.addMVar(
            shape=(self.N,),
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )
        # binaries
        U = model.addMVar(
            shape=(self.N, 3),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER   
        )

        for i in range(self.N):
            # positive
            model.addGenConstrIndicator(
                U[i,0], 1, a@X[i] - b >= self.delta
            )
            # negative
            model.addGenConstrIndicator(
                U[i,2], 1, a@X[i] - b <= -self.delta   
            )
            # zero
            model.addGenConstrIndicator(
                U[i,1], 1, a@X[i] - b <= self.delta - eps   
            )
            model.addGenConstrIndicator(
                U[i,1], 1, a@X[i] - b >= -self.delta + eps   
            )

            # SOS constraint
            model.addConstr(
                U[i,0] + U[i,1] + U[i,2] == 1
            )

            # trit
            model.addConstr(
                self.Z[i] == U[i,0] - U[i,2]   
            )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        model.addConstr(
            self.Z[t] == TRUE   
        )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """

        # only one temporal dimension
        i, j = key

        return self.Z[i]

     
    
class Not(Node):
    """Negation.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        child: Node
    ) -> None:
        """

        """

        self.N = child.N

        self.Z = model.addMVar(
            shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            for j in range(i, self.N):
                model.addConstr(
                    # notice how indexing is done on (potentially) timed formulas
                    self[i,j] ==  -child[i,j]
                )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """
        
        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]
    
class Or(Node):
    """Disjunction.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        left_child: Node,
        right_child: Node
    ) -> None:
        """

        """

        assert left_child.N == right_child.N

        self.N = left_child.N

        self.Z = model.addMVar(
            shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            for j in range(i, self.N):
                model.addGenConstrMax(
                    resvar=self[i, j],
                    vars=[left_child[i, j], right_child[i, j]]
                )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]
                 
class And(Node):
    """Conjunction.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        left_child: Node,
        right_child: Node
    ) -> None:
        """

        """

        assert left_child.N == right_child.N

        self.N = left_child.N

        self.Z = model.addMVar(
            shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            for j in range(i, self.N):
                model.addGenConstrMin(
                    resvar=self[i, j],
                    vars=[left_child[i, j], right_child[i, j]]
                )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]
    
class Always(Node):
    """Always.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        child: Node,
        a: int,
        b: int,
    ) -> None:
        """

        """

        self.N = child.N
        self.a = a
        self.b = b

        self.Z = model.addMVar(
            shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            for j in range(i, self.N):
                
                # case: b + i <= j [eq. (4)]
                if self.b + i <= j:
                    _vars = []
                    for t in range(a+i, b+i):
                        _vars.append(child[t, j])
                    model.addGenConstrMin(
                        resvar=self[i, j],
                        vars=_vars   
                    )

                # case: b + i > j [eq. (5)]
                # either running or failed
                elif self.b + i > j:
                    _vars = []
                    for t in range(a+i, j):
                        _vars.append(child[t, j])
                    
                    model.addGenConstrMin(
                        resvar=self[i, j],
                        vars=_vars,
                        constant=UNKNOWN
                    )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]

class Eventually(Node):
    """Eventually.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        child: Node,
        a: int,
        b: int,
    ) -> None:
        """

        """

        self.N = child.N
        self.a = a
        self.b = b

        self.Z = model.addMVar(
            shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            for j in range(i, self.N):
                
                # case: b + i <= j [eq. (4) with disjunction]
                if self.b + i <= j:
                    _vars = []
                    for t in range(a+i, b+i):
                        _vars.append(child[t, j])
                    model.addGenConstrMax(
                        resvar=self[i, j],
                        vars=_vars   
                    )

                # case: b + i > j [eq. (5) with disjunction]
                # either running or failed
                elif self.b + i > j:
                    _vars = []
                    for t in range(a+i, j):
                        _vars.append(child[t, j])
                    
                    model.addGenConstrMax(
                        resvar=self[i, j],
                        vars=_vars,
                        constant=UNKNOWN
                    )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]
    
class Selector(Node):
    """Selector.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        left_child: Node,
        right_child: Node,
        top_level: bool = False
    ) -> None:
        """

        """

        assert left_child.N == right_child.N

        self.N = left_child.N

        self.top_level: bool = top_level

        if self.top_level:
            # only really need one integer variable in this case
            self.Z = model.addVar(
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER   
            )
            # self.Z = z_{0, N}
            Y = []
            for j in range(self.N-1):
                Y = Y + [left_child[0,j], right_child[j+1,self.N-1]]
            
            model.addGenConstrMax(
                resvar=self.Z,
                vars=Y  
            )

            # enforce
            model.addConstr(
                self.Z == 1   
            )
        
        else:
            self.Z = model.addMVar(
                shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER
            )

            for i in range(self.N): # s_1
                for j in range(i, self.N): # s_2
                    
                    # j  necessarily need be greater than or equal to i+1 ?
                    # case 1: s_1 == s_2
                    if i == j:
                        # z^1_{i,i} may be satisfactory (if it is a predicate)
                        model.addGenConstrMax(
                            resvar=self[i, j],
                            vars=[left_child[i, j]],
                            constant=UNKNOWN   
                        )
                    # j > i
                    elif j == i + 1:
                        # wierd case best just to handle it by itself

                        # only one case
                        model.addGenConstrMax(
                            resvar=self[i,j],
                            vars=[left_child[i,j], right_child[i+1,j]]   
                        )
                    
                    else:
                        # j > i+1
                        # multiple cases
                        # Y = model.addMVar(
                        #     shape=(j-i-1,),
                        #     lb=FALSE,
                        #     ub=TRUE,
                        #     vtype=GRB.INTEGER   
                        # )

                        # all disjunctions so
                        Y = []
                        for k in range(j-i-1):
                            Y = Y + [left_child[i,i+k], right_child[i+k+1,j]]
                        
                        model.addGenConstrMax(
                            resvar=self[i,j],
                            vars=Y 
                        )

    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        if self.top_level:
            # constraint already added in init
            return

        assert t <= self.N # can be satisfied at last time step

        Z = model.addVar(
            lb=FALSE,
            ub=TRUE,
            vtype=GRB.INTEGER   
        )

        model.addGenConstrMax(
            resvar=Z,
            vars=[self[t,i] for i in range(t, self.N)]  
        )

        model.addConstr(
            Z == 1   
        )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        if self.top_level:
            return self.Z

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]
    
class Sequence(Node):
    """Sequence.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        left_child: Node,
        right_child: Node,
        top_level: bool = False
    ) -> None:
        """

        """

        assert left_child.N == right_child.N

        self.N = left_child.N
        
        self.top_level: bool = top_level

        if self.top_level:
            # only really need one integer variable in this case
            self.Z = model.addVar(
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER   
            )
            # self.Z = z_{0, N}
            Y = model.addMVar(
                shape=(self.N-1,),
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER   
            )
            for j in range(self.N-1):
                model.addGenConstrMin(
                    resvar=Y[j],
                    vars=[left_child[0,j], right_child[j+1,self.N-1]]   
                )
            
            model.addGenConstrMax(
                resvar=self.Z,
                vars=Y.tolist()   
            )

            # enforce
            model.addConstr(
                self.Z == 1   
            )
        
        else:
            self.Z = model.addMVar(
                shape=(self.N*(self.N+1)//2,), # upper triangular in 1D
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER
            )

            for i in range(self.N): # s_1
                for j in range(i, self.N): # s_2
                    
                    # j  necessarily need be greater than or equal to i+1 ?
                    # case 1: s_1 == s_2
                    if i == j:
                        # z^1_{i,i} may fail (if it is a predicate)
                        model.addGenConstrMin(
                            resvar=self[i, j],
                            vars=[left_child[i, j]],
                            constant=UNKNOWN   
                        )
                    # j > i
                    elif j == i + 1:
                        # wierd case best just to handle it by itself

                        # only one case
                        model.addGenConstrMin(
                            resvar=self[i,j],
                            vars=[left_child[i,j], right_child[i+1,j]]   
                        )
                    
                    else:
                        # j > i+1
                        # multiple cases
                        Y = model.addMVar(
                            shape=(j-i-1,),
                            lb=FALSE,
                            ub=TRUE,
                            vtype=GRB.INTEGER   
                        )

                        for k in range(j-i-1):
                            model.addGenConstrMin(
                                resvar=Y[k],
                                vars=[left_child[i,i+k], right_child[i+k+1,j]]
                            )
                        
                        model.addGenConstrMax(
                            resvar=self[i,j],
                            vars=Y.tolist()
                        )

    def enforce(
        self,
        model: gp.Model,
        t: int,
        any: bool=True
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        if self.top_level:
            # constraint already added in init
            return
        
        assert t <= self.N - 1 # cannot be satisfied at last time step
        
        if any:
            Z = model.addVar(
                lb=FALSE,
                ub=TRUE,
                vtype=GRB.INTEGER   
            )

            model.addGenConstrMax(
                resvar=Z,
                vars=[self[t,i] for i in range(t, self.N)]  
            )

            model.addConstr(
                Z == 1   
            )

        else:
            model.addConstr(
                sum(
                    [self[t, i] for i in range(self.N)]
                ) == 1
            )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        if self.top_level:
            return self.Z

        # two temporal dimensions
        i, j = key

        # upper triangular in 1D
        return self.Z[i*(2*self.N-i-1)//2 + j]

class BoxConstraint(Node):
    """

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        X: gp.MVar,
        x_min: list[float | None],
        x_max: list[float | None],
        delta: float | None = None
    ) -> None:
        """

        """

        self.N = X.shape[0]

        n = X.shape[1]

        assert len(x_min) == n and len(x_max) == n

        if delta is not None:
            assert delta > 0

        self.Z = model.addMVar(
            shape=(self.N,),
            lb=FALSE, # is this readable?
            ub=TRUE,  # or is this stupid
            vtype=GRB.INTEGER
        )

        constraints = []
        for i in range(n):
            a = np.zeros(n)
            a[i] = 1

            if x_min[i] is not None:
                if delta is None:
                    constraints.append(
                        LinearPredicate(
                            model,
                            X,
                            a,
                            x_min[i]
                        )   
                    )
                else:
                    constraints.append(
                        TernaryPredicate(
                            model,
                            X,
                            a,
                            x_min[i],
                            delta
                        )   
                    )
                    
            
            if x_max[i] is not None:
                if delta is None:
                    constraints.append(
                        LinearPredicate(
                            model,
                            X,
                            -a,
                            -x_max[i]
                        )   
                    )
                else:
                    constraints.append(
                        TernaryPredicate(
                            model,
                            X,
                            -a,
                            -x_max[i],
                            delta
                        )   
                    )
                    

        for i in range(self.N):
            model.addGenConstrMin(
                resvar=self.Z[i],
                vars=[c.Z[i] for c in constraints]   
            )
    
    def enforce(
        self,
        model: gp.Model,
        t: int
    ) -> None:
        """

        """

        # enforce satisfaction at time step t

        assert t <= self.N

        model.addConstr(
            self.Z[t] == TRUE   
        )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """

        # only one temporal dimension
        i, j = key
        
        return self.Z[i]

class Constant(Node):
    """Constant.

    ...
    """

    def __init__(
        self,
        model: gp.Model,
        N: int,
        val: K3
    ) -> None:
        """Constant.

        """

        self.N = N
        self.val = val

        self.Z = model.addMVar(
            shape=(self.N,),
            lb=FALSE, # is this readable?
            ub=TRUE,  # or is this stupid
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            model.addConstr(
                self.Z[i] == self.val   
            )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """

        # only one temporal dimension
        i, j = key
        
        return self.Z[i]