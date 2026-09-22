"""The requirement partition the IDDMBSE trade-off stage runs on.

Before MBO or DDO does anything, every requirement is put in one of two classes
by whether satisfaction can be checked offline or only by running the stack.
That split fixes what the model-based stage proves and what the data-driven
stage has to measure.

The file this reads is `case-studies/sensor-suite/requirements.yaml`, which
carries the 23 SysML requirements of the AGR_stack model with their class,
their reason, the tool stage that checks them and, where one applies, which of
the four local oracles bears on them.

Built for this release; the SysML model itself carries no such split.
"""

import pathlib

import yaml

DEFAULT_PATH = (pathlib.Path(__file__).resolve().parent.parent
                / "case-studies" / "sensor-suite" / "requirements.yaml")

CLASSES = ("model-based", "data-driven")
STAGES = ("MBO", "DDO", "MAVF")
METRICS = ("cost", "RAM", "power", "coverage")


def load(path=None):
    """Read the requirement list and check every entry is well formed."""
    p = pathlib.Path(path) if path else DEFAULT_PATH
    reqs = yaml.safe_load(p.read_text())
    if not isinstance(reqs, list) or not reqs:
        raise ValueError("requirements file must hold a non-empty list")
    seen = set()
    for r in reqs:
        for field in ("id", "name", "text", "class", "stage", "metric", "reason"):
            if field not in r:
                raise ValueError("requirement is missing " + field + ": " + str(r))
        if r["id"] in seen:
            raise ValueError("duplicate requirement id " + str(r["id"]))
        seen.add(r["id"])
        if r["class"] not in CLASSES:
            raise ValueError("bad class on " + str(r["id"]) + ": " + str(r["class"]))
        if r["stage"] not in STAGES:
            raise ValueError("bad stage on " + str(r["id"]) + ": " + str(r["stage"]))
        if r["metric"] is not None and r["metric"] not in METRICS:
            raise ValueError("bad metric on " + str(r["id"]) + ": " + str(r["metric"]))
    return reqs


def partition(reqs=None):
    """The two classes, as (model_based, data_driven) lists in file order."""
    reqs = reqs if reqs is not None else load()
    model_based = [r for r in reqs if r["class"] == "model-based"]
    data_driven = [r for r in reqs if r["class"] == "data-driven"]
    return model_based, data_driven


def by_stage(reqs=None):
    """Requirements grouped by the tool stage that checks them."""
    reqs = reqs if reqs is not None else load()
    return {s: [r for r in reqs if r["stage"] == s] for s in STAGES}


def metric_map(reqs=None):
    """{requirement id: metric name} for the requirements an oracle bears on.

    This is what `tradesx.sensitivity.rank_requirements` takes.
    """
    reqs = reqs if reqs is not None else load()
    return {r["id"]: r["metric"] for r in reqs if r["metric"] is not None}


def table(reqs=None):
    """The partition as printable lines, one per requirement."""
    reqs = reqs if reqs is not None else load()
    lines = []
    for r in reqs:
        lines.append(str(r["id"]).ljust(8) + str(r["class"]).ljust(13)
                     + str(r["stage"]).ljust(6) + str(r["metric"] or "-").ljust(10)
                     + r["name"])
    return lines
