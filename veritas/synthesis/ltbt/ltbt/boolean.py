import numpy as np
import gurobipy as gp

from gurobipy import GRB

import matplotlib.pyplot as plt

eps = 1e-6
M = 1e3


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
    
    def __call__(self, i: int, j: int) -> gp.Var:
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
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        # z=1  => ax>=b
        # z=0 => ax<b

        for i in range(self.N):
            model.addGenConstrIndicator(
                self.Z[i], 1, a@X[i] >= b   
            )
            model.addGenConstrIndicator(
                self.Z[i], 0, a@X[i] <= b-eps
            )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """
        
        return self.Z[key]
    
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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            model.addConstr(
                self.Z[i] == 1 - child.Z[i]
            )
    
    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
    
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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER   
        )

        for i in range(self.N):
            model.addGenConstrOr(
                resvar=self.Z[i],
                vars=[left_child.Z[i], right_child.Z[i]]
            )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
                 
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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER   
        )

        for i in range(self.N):
            model.addGenConstrAnd(
                resvar=self.Z[i],
                vars=[left_child.Z[i], right_child.Z[i]]
            )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
    
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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            _vars = child.Z[self.a+i:self.b+i].tolist()
            if _vars:
                model.addGenConstrAnd(
                    resvar=self.Z[i],
                    vars=_vars
                )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]

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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        for i in range(self.N):
            _vars = child.Z[self.a+i:self.b+i].tolist()
            if _vars:
                model.addGenConstrOr(
                    resvar=self.Z[i],
                    vars=_vars
                )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
    
class Selector(Node):
    """Selector.

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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        not_left_child = Not(model, left_child)

        # constrain
        for i in range(self.N):
            outer = model.addMVar(
                shape=(self.N-1-i,),
                lb=0,
                ub=1,
                vtype=GRB.INTEGER
            )

            
            for j in range(i, self.N-1):
                conjunct = model.addVar(0, 1, vtype=GRB.INTEGER)
                inner = not_left_child.Z[i:j+1].tolist()
                inner.append(right_child.Z[j+1])

                model.addGenConstrAnd(
                    resvar=conjunct,
                    vars=inner
                )
                model.addGenConstrOr(
                    resvar=outer[j-i],
                    vars=[left_child.Z[j], conjunct]
                )
            
            model.addGenConstrOr(
                resvar=self.Z[i],
                vars=outer.tolist()   
            )

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
    
class Sequence(Node):
    """Sequence.

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
            shape=(self.N,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        neg_Z = model.addMVar(
            shape=(self.N-1,),
            lb=0,
            ub=1,
            vtype=GRB.INTEGER
        )

        not_left_child = Not(model, left_child)
        not_right_child = Not(model, right_child)

        # constrain
        for i in range(self.N-1): # impossible to satisfy in one time step
            outer = model.addMVar(
                shape=(self.N-1-i,),
                lb=0,
                ub=1,
                vtype=GRB.INTEGER
            )

            for j in range(i, self.N-1):
                disjunct = model.addVar(0, 1, vtype=GRB.INTEGER)
                conjunct = model.addVar(0, 1, vtype=GRB.INTEGER)

                inner = left_child.Z[i:j+1].tolist()
                
                model.addGenConstrOr(
                    resvar=disjunct,
                    vars=inner
                )

                model.addGenConstrAnd(
                    resvar=conjunct,
                    vars=[disjunct, not_right_child.Z[j+1]]
                )

                model.addGenConstrOr(
                    resvar=outer[j-i],
                    vars=[not_left_child.Z[j], conjunct]
                )
            
            model.addGenConstrAnd(
                resvar=neg_Z[i],
                vars=outer.tolist()   
            )

            model.addConstr(
                self.Z[i] == 1 - neg_Z[i]
            )

            # yikes

    def __getitem__(self, key) -> gp.Var:
        """

        """

        return self.Z[key]
    
def sel_test(
    model: gp.Model,
    left_child: Node,
    right_child: Node
) -> gp.Var:
    """

    """

    l_vars = left_child.Z[:-1].tolist()
    r_vars = right_child.Z[1:].tolist()

    z = model.addVar(
        lb=0,
        ub=1,
        vtype=GRB.INTEGER   
    )

    model.addGenConstrOr(
        resvar=z,
        vars=l_vars+r_vars
    )

    return z

def seq_test(
    model: gp.Model,
    left_child: Node,
    right_child: Node
) -> gp.Var:
    """

    """

    N = left_child.N

    y = model.addMVar(
        shape=(N-1,),
        lb=0,
        ub=1,
        vtype=GRB.BINARY   
    )

    for i in range(N-1):
        model.addGenConstrAnd(
            resvar=y[i],
            vars=[left_child.Z[i], right_child.Z[i+1]]
        )    

    z = model.addVar(
        lb=0,
        ub=1,
        vtype=GRB.BINARY
    )

    model.addGenConstrOr(
        resvar=z,
        vars=y.tolist()
    )

    return z