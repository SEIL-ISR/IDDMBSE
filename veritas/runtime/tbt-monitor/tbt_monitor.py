

# x: list where the index "i" is the observation at time=i*dt
# a rho_phi is a callable that takes x at any time and returns the
# robustenss of phi w.r.t x as well as the boolean evaluation in {-1, 0, 1}

class compose_seq:
    """
    """

    def __init__(self, *rhos: callable):
        """
        """

        self._idx=0
        self._N=len(rhos)
        self._rhos=rhos
        self._curr_node=0
        self._rob=[]
        self._prev_state=0
    
    def __call__(self, x):
        """
        """

        if self._prev_state==-1: # seq has failed
            return min(self._rob), -1
        
        if self._prev_state==1: # seq has succeeded
            return min(self._rob), 1

        rho, state=self._rhos[self._curr_node](x[self._idx:])

        if state==-1: # failure
            self._rob.append(rho)
            self._prev_state=-1
            self._idx=len(x)

            return min(self._rob), -1
        
        elif state==1: # success
            self._curr_node+=1 # increment node
            # print(f"{self._curr_node}/{self._N}")
            self._rob.append(rho)
            self._idx=len(x)

            if self._curr_node==self._N: # last node, seq executed successfully
                self._prev_state=1
                return min(self._rob), 1
            else:
                self._prev_state=0
                return min(self._rob), 0
        
        elif state==0: # running
            self._prev_state=0

            if self._rob:
                return min(rho, *self._rob), 0
            else:
                return rho, 0


class compose_sel:
    """
    """

    def __init__(self, *rhos: callable):
        """
        """

        self._idx=0
        self._N=len(rhos)
        self._rhos=rhos
        self._curr_node=0
        self._rob=[]
        self._prev_state=0
    
    def __call__(self, x):
        """
        """

        if self._prev_state==-1: # sel has failed
            return max(self._rob), -1
        
        if self._prev_state==1: # sel has succeeded
            return max(self._rob), 1

        rho, state=self._rhos[self._curr_node](x[self._idx:])

        if state==1: # success
            self._rob.append(rho)
            self._prev_state=1
            self._idx=len(x)

            return min(self._rob), 1
        
        elif state==-1: # failure
            self._curr_node+=1 # increment node
            self._rob.append(rho)
            self._idx=len(x)

            if self._curr_node==self._N: # last node, sel executed to failure
                self._prev_state=-1
                return max(self._rob), -1
            else:
                self._prev_state=0
                return max(self._rob), 0
        
        elif state==0: # running
            self._prev_state=0

            if self._rob:
                return max(rho, *self._rob), 0
            else:
                return rho, 0


class compose_par:
    """
    """

    def __init__(self, *rhos: callable, M=None, K=None):
        """
        """

        self._rhos=rhos
        self._N=len(rhos)
        self._M=M
        self._K=K
        self._r_set=[i for i in range(self._N)]
        self._s_set=[]
        self._f_set=[]
        self._prev_state=0

    def __call__(self, x):
        """
        """

        temp=[]

        for i in self._r_set:
            rho, state=self._rhos[i](x)
            if state==-1: # failed
                self._f_set.append(rho)
                self._r_set.remove(i)
            elif state==1: # succeeded
                self._s_set.append(rho)
                self._r_set.remove(i)
            elif state==0:
                temp.append(rho)
        

        if len(self._s_set)>=self._M: # success takes priority in the event M and K become at the same time
            self._prev_state=1
            return min(self._s_set), 1
        elif len(self._f_set)>=self._K:
            self._prev_state=-1
            return max(self._f_set), -1
        
        self._prev_state=0 # redundant
        return sorted(temp+self._f_set+self._s_set)[-self._M], 0