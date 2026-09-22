import sys
import numpy as np
import rtamt

from tbt_monitor import *

def transform(traj, type='c'):
    '''
    :param type: 'c' for continuous/dense, 'd' for discrete time signal
    '''
    L = len(traj)
    t = np.arange(L)
    if type == 'c':
        # Continuous/dense specifications need a 2-D array where first column is the timestep and second column is the signal
        data = list(zip(t, traj))
    elif type == 'd':
        # Discrete specifications need a dictionary with explicit keys for time and signal name
        data = {'time': list(t), 'x': traj}
    return data


def monitor(data, phi_name, phi_formula):
    type = 'd'  # 'c' for continuous/dense and 'd' for discrete

    data = transform(data, type)

    if type == 'd':
        spec = rtamt.StlDiscreteTimeSpecification(
            semantics=rtamt.Semantics.STANDARD)
    elif type == 'c':
        spec = rtamt.StlDenseTimeSpecification(
            semantics=rtamt.Semantics.STANDARD)
    spec.name = phi_name
    spec.declare_var('x', 'float')
    spec.spec = phi_formula
    try:
        spec.parse()
        # spec.pastify()
    except rtamt.STLParseException as err:
        print('STL Parse Exception: {}'.format(err))
        sys.exit()

    if type == 'c':
        rob = spec.evaluate(['x', data])
    else:
        rob = spec.evaluate(data)


    return rob[0][1]

def get_status(rho):
    if rho > 0:
        return 1
    else:
        return 0

def evaluate_reach_object(x):
    phi = "eventually(x < 0.1)"
    if len(x) > 1:
        rho = monitor(x[:,0], "phi", phi)
    else:
        rho = 0
    print("BT Leaf Node: Reach")
    return rho, get_status(rho)

def evaluate_grasp(x):
    phi = "eventually(x < 0.05)"
    if len(x) > 1:
        rho = monitor(x[:,1], "phi", phi)
    else:
        rho = 0
    print("BT Leaf Node: Grasp")
    return rho, get_status(rho)

def evaluate_reach_goal(x):
    phi = "eventually(x < 0.05)"
    if len(x) > 1:
        rho = monitor(x[:,2], "phi", phi)
    else:
        rho = 0
    print("BT Leaf Node: Goal")
    return rho, get_status(rho)

def evaluate(tbt, data):
    data = np.array(data)
    
    rho, status = tbt(data)
    return rho, status