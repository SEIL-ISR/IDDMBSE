"""STL monitors built from a YAML observer spec.

This is the part of the runtime module that has nothing to do with ROS, so the same monitors
run inside the ROS 2 node (`stl_observer_node.py`) and over a recorded CSV
(`replay_observer.py`).

A spec file is

    rate: 10.0                     # Hz; the observer samples every signal at this rate
    monitors:
      - name: soc_safety
        requirement: P.1.4         # the SysML requirement this obligation comes from
        formula: "historically (soc >= 0.6)"
        pastify: false             # true for bounded-future formulas (always[0,T], eventually[0,T])
        warmup: 0.0                # seconds before a negative robustness counts as a violation
        signals:
          soc:
            topic: /battery_state
            type: sensor_msgs/msg/BatteryState
            field: percentage

The formula is RTAMT STL.  RTAMT's online monitor implements past-time operators only
(`historically`, `once`, `since`, and their bounded forms), so a safety obligation is written
directly as `historically (p)` and a bounded-future one as `always[0,T] (p)` plus
`pastify: true`, which RTAMT rewrites into the past.  Interval bounds are in seconds: the
sampling period is handed to RTAMT so `once[0,180]` really means the last 180 seconds.

`field` is a dotted path into the message, so `percentage`, `pose.position.x` and `ranges.0`
all work.  The value is cast to float, which turns a Bool field into 1.0 / 0.0 -- that is the
"Booleanizer" direction the long-form report describes, a predicate over the real signal
(`goal >= 0.5`) standing in for the Boolean.
"""

import rtamt
import yaml


def read_field(msg, path):
    """Pull one number out of a message along a dotted path. Integer parts index sequences."""
    v = msg
    for part in path.split("."):
        v = v[int(part)] if part.lstrip("-").isdigit() else getattr(v, part)
    return float(v)


class Monitor:
    """One STL obligation, updated one sample at a time."""

    def __init__(self, name, formula, signals, period, pastify=False, warmup=0.0, requirement=""):
        self.name = name
        self.formula = formula
        self.signals = list(signals)
        self.period = period
        self.warmup = warmup
        self.requirement = requirement
        self.spec = rtamt.StlDiscreteTimeSpecification(semantics=rtamt.Semantics.STANDARD)
        self.spec.name = name
        for s in self.signals:
            self.spec.declare_var(s, "float")
        self.spec.set_sampling_period(int(round(period * 1000)), "ms", 0.1)
        self.spec.spec = formula
        self.spec.parse()
        if pastify:
            self.spec.pastify()
        self.k = 0
        self.rho = None
        self.violated = False

    def step(self, values):
        """Feed one sample. Returns (robustness, violated)."""
        t = self.k * self.period
        self.rho = self.spec.update(self.k, [(s, float(values[s])) for s in self.signals])
        self.k += 1
        self.violated = self.rho < 0 and t >= self.warmup
        return self.rho, self.violated

    @property
    def time(self):
        """Timestamp of the last sample fed, in seconds since the first."""
        return (self.k - 1) * self.period


def load_spec(path):
    """Read a YAML observer spec. Returns (rate, [Monitor], {signal: {topic,type,field}})."""
    cfg = yaml.safe_load(open(path))
    rate = float(cfg["rate"])
    period = 1.0 / rate
    monitors = []
    sources = {}
    for m in cfg["monitors"]:
        monitors.append(Monitor(
            m["name"], m["formula"], list(m["signals"]), period,
            pastify=bool(m.get("pastify", False)),
            warmup=float(m.get("warmup", 0.0)),
            requirement=m.get("requirement", ""),
        ))
        for name, src in m["signals"].items():
            if name in sources and sources[name] != src:
                raise ValueError("signal " + name + " is bound to two different sources")
            sources[name] = src
    return rate, monitors, sources
