import os
import pyuppaal
from pyuppaal.nta import Template, Location, Edge

# A global counter to uniquely identify Locations
_ID=0
# Global declarations
_DECLARATIONS={
    "urgent chan": ["success", "failure"],
    "urgent broadcast chan": []
}


class TA:
    """
    Helper class for Timed Automata.

    ...

    Attributes:
        _name: A name for the TA object.
        _locations: A list of Locations (states).
        _edges: A list of Edges (transitions).
        _params: A string of UPPAAL parameters.
        _declarations: A string of UPPAAL declarations.
    """

    def __init__(self):
        """Initialize an empty TA object.
        """

        self._name:        str        = None
        self._locations:   dict       = {}
        self._edges:       list[Edge] = []
        self._params:      str        = None
        self._declaration: str        = None
    
    def get_transitions(self, loc1: Location, loc2: Location) -> list[Edge]:
        """Returns the set of edges between two Locations.

        Args:
            loc1: A Location object within self._locations.
            loc2: A Location object within self._locations.
        
        Returns:
            A list of all edges between loc1 and loc2.
        """

        edges = []
        for edge in self._edges:
            if edge.source_location_id == loc1.location_id:
                if edge.target_location_id == loc2.location_id:
                    edges.append(edge)
    
            elif edge.source_location_id == loc2.location_id:
                if edge.target_location_id == loc1.location_id:
                    edges.append(edge)
        
        return edges
    
    def get_transitions_to(self, loc: Location) -> list[Edge]:
        """Returns all ingoing edges of a Location.

        Args:
            loc: A Location object within self._locations.
        
        Returns:
            A list of ingoing edges to loc.
        """

        edges = []
        for edge in self._edges:
            if edge.target_location_id == loc.location_id:
                edges.append(edge)
        
        return edges
    
    def get_transitions_from(self, loc: Location) -> list[Edge]:
        """Returns all outgoing edges of a Location

        Args:
            loc: A Location object within self._locations.
        
        Returns:
            A list of all outgoing edges from loc.
        """

        edges = []
        for edge in self._edges:
            if edge.source_location_id == loc.location_id:
                edges.append(edge)
        
        return edges
    
    @classmethod
    def load_from_template(cls, temp: Template):
        """Initalize a TA object from a pyuppaal Template.

        Args:
            temp: A Template object.
        
        Returns:
            A TA object initialized from temp.
        """

        rtn = cls()
        rtn._name = temp.name
        rtn._locations = {}

        for location in temp.locations:
            _ID = location.location_id
            if location.name == "Init":
                rtn._locations["init"] = location
                rtn._locations["init"].name = None
            elif location.name == "Success":
                rtn._locations["success"] = location
                rtn._locations["success"].name = None
            elif location.name == "Failure":
                rtn._locations["failure"] = location
                rtn._locations["failure"].name = None
            else:
                rtn._locations[_ID] = location
            _ID += 1

        rtn._edges = temp.edges
        rtn._params = temp.params
        rtn._declaration = temp.declaration

        return rtn
    
    def to_template(self) -> Template:
        """Convert TA to a pyuppaal Template.

        Returns:
            A Template object encoding a TA.
        """

        return Template(
            name        = self._name,
            locations   = self._locations.values(),
            edges       = self._edges,
            init_ref    = self._locations["init"].location_id,
            params      = self._params,
            declaration = self._declaration
        )


def compose_seq(
        *subs:  TA,
        name:   str  = None,
        root:   bool = False,
        params: str  = None
    ) -> TA:
    """Compose a sequence of TA into a single TA.

    Implements Alg. 1 which takes a list of subtree automata and
    composes them together into a BT equivalent sequence node.

    Args:
        subs: The subtree equivalent automata in the order in which
            they are to be executed.
        name: A string name for the equivalent TA.
        root: A Boolean indication if this node corresponds to the
            root of the BT
        params: A string of UPPAAL parameters.
    
    Returns:
        A TA object which represents the equivalent sequence composition
        of subs according to Alg. 1 in the paper.
    """

    if len(subs) == 1:
        return subs[0]

    rtn = TA()

    if name is not None:
        rtn._name = name
    else:
        rtn._name = "Sequence"

    if params is not None:
        rtn._params = params

    rtn._declaration = "clock t;"

    for i in range(len(subs)-1):
        for edge in subs[i].get_transitions_to(subs[i]._locations["success"]):
            edge.target_location_id = subs[i+1]._locations["init"].location_id
            edge.target_location_pos = subs[i+1]._locations["init"].location_pos
        
        for edge in subs[i].get_transitions_to(subs[i]._locations["failure"]):
            edge.target_location_id = subs[-1]._locations["failure"].location_id
            edge.target_location_pos = subs[-1]._locations["failure"].location_pos
        
        del subs[i]._locations["success"]
        del subs[i]._locations["failure"]
    
    for i in range(1, len(subs)):
        id = subs[i]._locations["init"].location_id
        subs[i]._locations[id] = subs[i]._locations.pop("init")

    # amungst all dictionaries, should have one init, success, and
    # failure state respectively
    for sub in subs:
        rtn._locations.update(sub._locations)
        rtn._edges += sub._edges

    if root:
        rtn._locations["init"].is_initial = True
        rtn._locations["success"].name = "Success"
        rtn._locations["failure"].name = "Failure"
    
    return rtn


def compose_sel(
        *subs:  TA,
        name:   str  = None,
        root:   bool = False,
        params: str  = None
    ) -> TA:
    """Compose a selection of TA into a single TA.

    Implements complement of Alg. 1 which takes a list of
    subtree automata and composes them together into a BT
    equivalent selector node.

    Args:
        subs: The subtree equivalent automata in the order in which
            they are to be executed.
        name: A string name for the equivalent TA.
        root: A Boolean indication if this node corresponds to the
            root of the BT
        params: A string of UPPAAL parameters.
    
    Returns:
        A TA object which represents the equivalent selector composition
        of subs according to complement of Alg. 1 in the paper.
    """

    if len(subs) == 1:
        return subs[0]

    rtn=TA()

    if name is not None:
        rtn._name = name
    else:
        rtn._name = "Selector"

    if params is not None:
        rtn._params = params

    rtn._declaration="clock t;"

    for i in range(len(subs)-1):
        for edge in subs[i].get_transitions_to(subs[i]._locations["failure"]):
            edge.target_location_id = subs[i+1]._locations["init"].location_id
            edge.target_location_pos = subs[i+1]._locations["init"].location_pos
        
        for edge in subs[i].get_transitions_to(subs[i]._locations["success"]):
            edge.target_location_id = subs[-1]._locations["success"].location_id
            edge.target_location_pos = subs[-1]._locations["success"].location_pos
        
        del subs[i]._locations["success"]
        del subs[i]._locations["failure"]

    for i in range(1, len(subs)):
        id = subs[i]._locations["init"].location_id
        subs[i]._locations[id] = subs[i]._locations.pop("init")

    # amungst all dictionaries, should have one init, success, and
    # failure state respectively
    for sub in subs:
        rtn._locations.update(sub._locations)
        rtn._edges += sub._edges

    if root:
        rtn._locations["init"].is_initial = True
        rtn._locations["success"].name = "Success"
        rtn._locations["failure"].name = "Failure"

    return rtn


def compose_par(
        *subs:  TA,
        M:      int  = None,
        K:      int  = None,
        name:   str  = None,
        root:   bool = False,
        params: str  = None
        ) -> tuple[TA, list[TA]]:
    """Compose subtrees TA into a parallel NTA.

    Implements Alg. 2 which takes a list of subtree automata and
    composes them together into a BT equivalent parallel node.

    Args:
        subs: The subtree equivalent automata in the order in which
            they are to be executed.
        M: Integer success conditions 1<=M<=N.
        K: Integer failure conditions 1<=K<=N-M+1.
        name: A string name for the equivalent TA.
        root: A Boolean indication if this node corresponds to the
            root of the BT
        params: A string of UPPAAL parameters.
    
    Returns:
        A tuple containing the parallel TA and the synchronized subtree
        TAs as a list of TA. 
    """

    global _ID

    for sub in subs:
        sub._locations["success"].is_urgent = False
        sub._locations["failure"].is_urgent = False
        sub._locations["init"].is_initial = False
        id=sub._locations["init"].location_id
        sub._locations[id] = sub._locations.pop("init")
        sub._locations["init"] = Location(
            location_id = _ID,
            location_pos = (0,0),
            is_initial = True
        )
        _ID += 1
        sub._edges.append(
            Edge(
                source_location_id = sub._locations["init"].location_id,
                source_location_pos = sub._locations["init"].location_pos,
                target_location_id = sub._locations[id].location_id,
                target_location_pos = sub._locations[id].location_pos,
                sync = "run?" # NEEDS TO BE PROGRAMATICALLY ASSIGNED AS
                              # IT NEEDS TO BE UNIQUE FOR ALL PARALLEL NODES
        ))
        for e in sub.get_transitions_to(sub._locations["success"]):
            e.sync = "success!"
        for e in sub.get_transitions_to(sub._locations["failure"]):
            e.sync = "failure!"
    
    par = TA()

    if name is not None:
        par._name = name
    else:
        par._name = "Parallel"
    
    if params is not None:
        par._params = params

    # locations
    par._locations["init"]=Location(
        location_id = _ID,
        location_pos = (0,0) # maybe change in future so TA aren't all
                             # stacked on top of eachother
    )
    _ID += 1 # important!

    par._locations["success"]=Location(
        location_id = _ID,
        location_pos = (0,0)
    )
    _ID += 1

    par._locations["failure"] = Location(
        location_id = _ID,
        location_pos = (0,0)
    )
    _ID += 1

    _intermediate = Location(
        location_id = _ID,
        location_pos = (0,0),
        invariant = f"s<{M} && f<{K}"
    )
    par._locations[_ID] = _intermediate
    _ID += 1

    if root:
        par._locations["init"].is_initial = True
        par._locations["success"].name = "Success"
        par._locations["failure"].name = "Failure"
    
    # edges
    par._edges = [
        Edge(
            source_location_id = par._locations["init"].location_id,
            source_location_pos = par._locations["init"].location_pos,
            target_location_id = _intermediate.location_id,
            target_location_pos = _intermediate.location_pos,
            sync = "run!"
        ),
        Edge(
            source_location_id = _intermediate.location_id,
            source_location_pos = _intermediate.location_pos,
            target_location_id = _intermediate.location_id,
            target_location_pos = _intermediate.location_pos,
            sync = "success?",
            update = "s++"
        ),
        Edge(
            source_location_id = _intermediate.location_id,
            source_location_pos = _intermediate.location_pos,
            target_location_id = _intermediate.location_id,
            target_location_pos = _intermediate.location_pos,
            sync = "failure?",
            update = "f++"
        ),
        Edge(
            source_location_id = _intermediate.location_id,
            source_location_pos = _intermediate.location_pos,
            target_location_id = par._locations["success"].location_id,
            target_location_pos = par._locations["success"].location_pos,
            guard = f"s>={M}"
        ),
        Edge(
            source_location_id = _intermediate.location_id,
            source_location_pos = _intermediate.location_pos,
            target_location_id = par._locations["failure"].location_id,
            target_location_pos = par._locations["failure"].location_pos,
            guard = f"f>={K}"
        )
    ]

    return par, subs


class Eventually(TA):
    """TA conversion for action nodes of the form <>_[0, T] P.

    Extends TA class.
    ... 
    """

    def __init__(self, prop: str):
        """Initialize an Eventually TA.

        Args:
            pred: A string containing an atomic proposition. 
        """

        global _ID

        TA.__init__(self)

        self._prop = prop.replace(" ", "") # no whitespace
        self._name = "F"+self._prop
        self._params = "const int T"
        self._declaration = "clock t;"

        # locations
        self._locations["init"] = Location(
            location_id = _ID,
            location_pos = (0,0) # maybe change in future so TA aren't all stacked on top of eachother
        )
        _ID += 1 # important!

        self._locations["success"] = Location(
            location_id = _ID,
            location_pos = (0,0),
            name = "Success"
        )
        _ID += 1

        self._locations["failure"] = Location(
            location_id = _ID,
            location_pos = (0,0),
            name = "Failure"
        )
        _ID += 1

        # edges

        self._edges = [
            Edge( # self transition
            source_location_id = self._locations["init"].location_id,
            source_location_pos = self._locations["init"].location_pos,
            target_location_id = self._locations["init"].location_id,
            target_location_pos = self._locations["init"].location_pos,
            guard = f"t<=T"
            ),
            Edge( # success transition
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = self._locations["success"].location_id,
                target_location_pos = self._locations["success"].location_pos,
                guard = self._prop+f" && x<={T}",
                update="t=0" # reset clock so other TA can use the same clock
            ),
            Edge( # failure transition
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = self._locations["failure"].location_id,
                target_location_pos = self._locations["failure"].location_pos,
                guard = f"t>T",
                update = "t=0"
            )
        ]


class Always(TA):
    """TA conversion for action nodes of the form []_[0, T] P.

    Extends TA class.
    ... 
    """

    def __init__(self, prop: str):
        """Initialize an Always TA.

        Args:
            prop: A string containing an atomic proposition.
        """

        global _ID

        TA.__init__(self)

        self._prop = prop.replace(" ", "") # no whitespace
        self._name = "G"+self._prop
        self._params = "const int t_max"
        self._declaration = "clock t;"

        # locations
        self._locations["init"] = Location(
            location_id = _ID,
            location_pos = (0,0), # maybe change in future so TA aren't all stacked on top of eachother
            is_urgent = True
        )
        _ID += 1 # important!

        # intermediate location
        _intermediate = Location(
            location_id = _ID,
            location_pos = (0,0),
            invariant = self._prop
        )
        self._locations[_ID] = _intermediate
        _ID += 1

        self._locations["success"] = Location(
            location_id = _ID,
            location_pos = (0,0)
        )
        _ID += 1

        self._locations["failure"] = Location(
            location_id = _ID,
            location_pos = (0,0)
        )
        _ID += 1

        # edges

        self._edges = [
            Edge( # init to intermediate
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = _intermediate.location_id,
                target_location_pos = _intermediate.location_pos,
                guard = self._prop
            ),
            Edge( # init to failure
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = self._locations["failure"].location_id,
                target_location_pos = self._locations["failure"].location_pos,
                guard = "!" + self._prop
            ),
            Edge( # self transition
                source_location_id = _intermediate.location_id,
                source_location_pos = _intermediate.location_pos,
                target_location_id = _intermediate.location_id,
                target_location_pos = _intermediate.location_pos,
                guard = self._prop + f" && t<=T"
            ),
            Edge( # success transition
                source_location_id = _intermediate.location_id,
                source_location_pos = _intermediate.location_pos,
                target_location_id = self._locations["success"].location_id,
                target_location_pos = self._locations["success"].location_pos,
                guard = self._prop + f" && t>=T",
                update = "x=0" # reset clock so other TA can use the same clock
            ),
            Edge( # failure transition
                source_location_id = _intermediate.location_id,
                source_location_pos = _intermediate.location_pos,
                target_location_id = self._locations["failure"].location_id,
                target_location_pos = self._locations["failure"].location_pos,
                guard = "!" + self._prop + f" && t<=T",
                update = "t=0"
            )
        ]


class Condition(TA):
    """TA conversion for condition nodes of the form P.
    
    Extends TA class.
    ...
    """

    def __init__(self, prop: str):
        """Initialize a Condition TA.

        Args:
            prop: A string containing an atomic proposition.
        """

        global _ID

        TA.__init__(self)

        self._prop = prop.replace(" ", "") # no whitespace
        self._name = self._prop

        # locations
        self._locations["init"] = Location(
            location_id = _ID,
            location_pos = (0,0),
            is_urgent = True
        )
        _ID += 1 # important!

        self._locations["success"] = Location(
            location_id = _ID,
            location_pos = (0,0)
        )
        _ID += 1

        self._locations["failure"] = Location(
            location_id = _ID,
            location_pos = (0,0)
        )
        _ID += 1

        # edges

        self._edges = [
            Edge( # success transition
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = self._locations["success"].location_id,
                target_location_pos = self._locations["success"].location_pos,
                guard = self._prop
            ),
            Edge( # failure transition
                source_location_id = self._locations["init"].location_id,
                source_location_pos = self._locations["init"].location_pos,
                target_location_id = self._locations["failure"].location_id,
                target_location_pos = self._locations["failure"].location_pos,
                guard = "!" + self._prop
            )
        ]


def gen_transition(
        N: int,
        M: int,
        dt: int=1,
        init: tuple[int, int]=None,
        **zones
    ) -> tuple[Template, dict[str, tuple[int, int]]]:
    r"""Generate a grid world transition system.

    Args:
        N: Number of rows in the grid world.
        M: Number of columns in the grid world.
        dt: Time elapsed per transition.
        init: Initial state in transition system, init \in [0,N-1] \times [0,M-1].
        zones: Kwargs of the form A=(1,2) meaning proposition A is true at position (1,2).

    Returns:
        A pyuppaal Template representing the transition system and a dict containing the zones.

    """

    space = 100
    locs = []
    edges = []
    id = 0
    for i in range(N):
        for j in range(M):
            locs.append(
                Location(
                    location_id = id,
                    location_pos = (space*j, space*i),
                    invariant = f"t<={dt}"
                )
            )
            id += 1

    if init:
        locs[init[0]*N+init[1]].is_initial = True
        init_ref = init[0]*N + init[1]
    else:
        locs[0].is_initial = True
        init_ref = 0

    for i in range(N):
        for j in range(M):
            # two possible nodes for each current one
            too = []
            if i + 1 < N:
                if j + 1 < M:
                    too.append((i+1,j))
                    too.append((i,j+1))
                else:
                    too.append((i+1,j))
            elif j + 1 < M:
                too.append((i,j+1))
            # else: do nothing
            # print(too)

            # self loop:
            edges.append(
                Edge(
                    source_location_id = i*N+j,
                    target_location_id = i*N+j,
                    source_location_pos = (space*j, space*i),
                    target_location_pos = (space*j, space*i),
                    guard = f"t=={dt}",
                    update = "t=0"
                )
            )
            for nd in too:
                E1 = Edge( # from from to to
                    source_location_id = i*N+j,
                    target_location_id = nd[0]*N+nd[1],
                    source_location_pos = (space*j, space*i),
                    target_location_pos = (space*nd[1], space*nd[0]),
                    guard = f"t=={dt}",
                    update = "t=0"
                )
                E2 = Edge( # from to to from
                    target_location_id = i*N+j,
                    source_location_id = nd[0]*N+nd[1],
                    target_location_pos = (space*j, space*i),
                    source_location_pos = (space*nd[1], space*nd[0]),
                    guard = f"t=={dt}",
                    update = "t=0"
                )

                if (i,j) in zones.values():
                    # from is a zone
                    # find zone name
                    for zn, ij in zones.items():
                        if ij == (i,j):
                            break
                    # exiting zone
                    E1.update += f", {zn}=false"
                    # entering zone
                    E2.update += f", {zn}=true"
                
                if nd in zones.values():
                    # to is a zone
                    for zn, ij in zones.items():
                        if ij == nd:
                            break
                    # entering zone
                    E1.update += f", {zn}=true"
                    # exiting zone
                    E2.update += f", {zn}=false"
                
                edges.append(E1)
                edges.append(E2)

    template=Template(
        name = "Grid",
        locations = locs,
        init_ref = init_ref,
        edges = edges,
        declaration = "clock t;"
    )

    return template, zones