"""Compile SysML state machines and activities into an UPPAAL network of timed automata.

This is the model-based module of VERITAS (paper Sec. III-D (i)): "compiles SysML
state-machine and activity diagrams into UPPAAL Networks of Timed Automata and discharges
proof obligations against contracts derived from requirements diagrams".

Input is a MagicDraw `.mdzip` (a zip whose member `com.nomagic.magicdraw.uml_model.model`
holds the XMI) or a bare XMI file.  Output is an UPPAAL 1.1 flat-system XML with one template
per state machine or activity, a queries block, and a warning for everything the supported
fragment could not express.

What the XMI looks like, and what this reads
--------------------------------------------
MagicDraw writes UML 2.5 XMI where the XML tag is the *role* (`packagedElement`,
`ownedBehavior`, `region`, `subvertex`, `transition`, `node`, `edge`) and the metaclass is the
attribute `xmi:type`.  So a state machine is `<ownedBehavior xmi:type='uml:StateMachine'>`,
never `<uml:StateMachine>`.  Requirements are the exception: they are stereotype applications
literally tagged `<sysml:Requirement Id='...' Text='...' base_Class='...'/>`.

State machines
  region > subvertex        uml:Pseudostate (initial), uml:State, uml:FinalState -> locations
  region > transition       source/target idrefs                                -> edges
  transition > trigger      @event idref into a top-level packagedElement:
                              uml:ChangeEvent > changeExpression > body   -> an edge guard
                              uml:TimeEvent   > when > expr @value        -> a clock guard
  subvertex > entry/exit/doActivity > body                                -> edge assignments

  There is no `<guard>` element in this dialect; the condition lives on the triggering
  ChangeEvent.  A transition's own `name` attribute sometimes carries an informal label
  ("when (x=0.7) && after(100)"); that text is never parsed, only copied into a comment and
  reported as a warning, because it is free text with no structured counterpart.

Activities
  node                      uml:InitialNode, uml:ActivityFinalNode, uml:OpaqueAction,
                            uml:CallBehaviorAction, uml:SendSignalAction, uml:MergeNode,
                            uml:ForkNode, uml:JoinNode, uml:DecisionNode, uml:CentralBufferNode
  edge                      uml:ControlFlow / uml:ObjectFlow, source/target idrefs; a flow
                            that starts or ends on a pin is lifted to the pin's owning action

  Every node becomes a location and every flow an edge, which is exact for the sequential
  fragment (initial -> actions -> final, with merges).  Fork and join are emitted as ordinary
  locations and reported as warnings: a fork then reads as a nondeterministic choice, not as
  concurrency, so a forked activity is *not* faithfully translated.  Decision guards are
  translated with the same expression translator as state-machine guards.

The supported expression fragment
---------------------------------
`var OP const` with OP in `< <= > >= == != =` and `const` a decimal number, plus `&&`-joined
conjunctions of those.  Real-valued variables are scaled to integers by a factor (default 100)
and declared `int`, because UPPAAL has no reals: `current_soc < 0.6` becomes
`current_soc < 60`.  A constant that is not integral after scaling is rounded and warned about.
Anything else -- function calls, arithmetic, references to other objects -- is dropped into a
comment and warned about.

Time
----
Each template gets a local `clock t`, reset on every edge, so `t` is the time spent in the
current location, and the model shares one `clock gt` that is never reset.  A TimeEvent with
`isRelative='true'` and value V becomes the guard `t >= V` on its edge, with the invariant
`t <= V` added to the source location when every outgoing edge of that location is a relative
TimeEvent (so the transition fires exactly at V, which is UML's `after(V)`).  A TimeEvent
without `isRelative` is an absolute time and becomes `gt >= V`, with a warning, since UPPAAL
cannot bound it from above without constraining the whole system.
"""

import argparse
import os
import re
import xml.etree.ElementTree as ET
import zipfile

XMI = "{http://www.omg.org/spec/XMI/20131001}"
SYSML = "{http://www.omg.org/spec/SysML/20181001/SysML}"
MODEL_MEMBER = "com.nomagic.magicdraw.uml_model.model"

DEFAULT_SCALE = 100

REL = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*(<=|>=|==|!=|<|>|=)\s*(-?[0-9]+(?:\.[0-9]+)?)\s*$")


# ------------------------------------------------------------------
# reading the model

def load_model(path):
    """Parse a .mdzip (its UML model member) or a bare XMI file. Returns the root element."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if MODEL_MEMBER not in names:
                raise ValueError(path + " is a zip but has no " + MODEL_MEMBER + " member")
            return ET.fromstring(z.read(MODEL_MEMBER))
    return ET.parse(path).getroot()


def index_model(root):
    """Return (by_id, parent) over the whole tree. The walk is over XML structure, not data."""
    by_id, parent = {}, {}
    stack = [(root, None)]
    while stack:
        el, up = stack.pop()
        parent[id(el)] = up
        i = el.get(XMI + "id")
        if i:
            by_id[i] = el
        for child in el:
            stack.append((child, el))
    return by_id, parent


def mtype(el):
    return el.get(XMI + "type", "")


def elements_of_type(root, uml_type):
    return [el for el in root.iter() if mtype(el) == uml_type]


def body_of(el):
    """Text of an OpaqueExpression/OpaqueBehavior <body> child, or None."""
    if el is None:
        return None
    b = el.find("body")
    return b.text if b is not None and b.text else None


def requirements(root):
    """Every <sysml:Requirement> stereotype application, with the name of the class it is on."""
    by_id, _ = index_model(root)
    out = []
    for el in root.iter(SYSML + "Requirement"):
        base = by_id.get(el.get("base_Class", ""))
        out.append({
            "id": el.get("Id", ""),
            "text": el.get("Text", ""),
            "name": (base.get("name", "") if base is not None else ""),
            "xmi_id": el.get(XMI + "id", ""),
        })
    return out


# ------------------------------------------------------------------
# expressions

def sanitize(name, fallback="n"):
    """Make an UPPAAL identifier out of a UML name."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return fallback
    return s if s[0].isalpha() or s[0] == "_" else "_" + s


def _scale_const(text, scale, warn, where):
    v = float(text) * scale
    r = int(round(v))
    if abs(v - r) > 1e-9:
        warn.append(where + ": constant " + text + " is not integral at scale " + str(scale)
                    + ", rounded to " + str(r))
    return r


def translate_expr(body, scale, warn, where, assignment=False):
    """Translate one `var OP const` term, or a && conjunction of them, to UPPAAL syntax.

    Returns (translated, unsupported): `translated` is the UPPAAL text or None, `unsupported`
    is the list of source terms that could not be translated.
    """
    if not body:
        return None, []
    parts = [p for p in re.split(r"&&", body) if p.strip()]
    ok, bad = [], []
    for p in parts:
        m = REL.match(p.replace("(", " ").replace(")", " "))
        if not m:
            bad.append(p.strip())
            continue
        var, op, const = m.group(1), m.group(2), m.group(3)
        if assignment:
            op = "="
        elif op == "=":
            op = "=="
        ok.append(var + " " + op + " " + str(_scale_const(const, scale, warn, where)))
    if bad:
        warn.append(where + ": cannot translate " + repr(" && ".join(bad))
                    + " (outside the var OP const fragment); kept as a comment")
    return (" && ".join(ok) if ok else None), bad


def variables_in(body):
    return set(m.group(1) for m in (REL.match(p.replace("(", " ").replace(")", " "))
                                    for p in re.split(r"&&", body or "")) if m)


# ------------------------------------------------------------------
# state machines

def event_of(transition, by_id):
    t = transition.find("trigger")
    if t is None:
        return None
    return by_id.get(t.get("event", ""))


def time_event_value(event):
    """(value, is_relative) of a uml:TimeEvent, or None."""
    when = event.find("when")
    expr = when.find("expr") if when is not None else None
    if expr is None or expr.get("value") is None:
        return None
    return expr.get("value"), event.get("isRelative", "false") == "true"


def behaviour_body(state, kind):
    child = state.find(kind)
    return body_of(child) if child is not None else None


def state_machine_template(sm, by_id, scale, warn):
    """One uml:StateMachine -> one template dict."""
    sm_name = re.sub(r"^SMD\s+", "", sm.get("name", "StateMachine"))
    name = sanitize(sm_name, "StateMachine")
    where = "state machine " + name

    states, transitions = [], []
    for region in sm.findall("region"):
        states += region.findall("subvertex")
        transitions += region.findall("transition")

    loc_name, init_ref = {}, None
    used = set()
    for s in states:
        sid = s.get(XMI + "id")
        base = sanitize(s.get("name", ""), mtype(s).split(":")[-1])
        n, k = base, 2
        while n in used:
            n, k = base + "_" + str(k), k + 1
        used.add(n)
        loc_name[sid] = n
        if mtype(s) == "uml:Pseudostate" and init_ref is None:
            init_ref = sid
            if s.get("kind") is None:
                warn.append(where + ": Pseudostate " + n
                            + " has no kind attribute, read as the initial pseudostate (the UML default)")
    if init_ref is None and states:
        init_ref = states[0].get(XMI + "id")
        warn.append(where + ": no Pseudostate found, using " + loc_name[init_ref] + " as the initial location")

    # entry behaviours become assignments on every edge entering the state
    entry_assign, variables = {}, set()
    for s in states:
        sid = s.get(XMI + "id")
        for kind in ["entry", "doActivity"]:
            b = behaviour_body(s, kind)
            if not b:
                continue
            a, _ = translate_expr(b, scale, warn, where + " " + kind + " of " + loc_name[sid], assignment=True)
            variables |= variables_in(b)
            if a:
                entry_assign.setdefault(sid, []).append(a)
            if kind == "doActivity":
                warn.append(where + ": doActivity of " + loc_name[sid] + " (" + b.strip()
                            + ") is applied once on entry; UPPAAL has no do-while-in-state behaviour")
        b = behaviour_body(s, "exit")
        if b:
            warn.append(where + ": exit behaviour of " + loc_name[sid] + " (" + b.strip() + ") is not translated")

    edges, relative_bound = [], {}
    for tr in transitions:
        src, tgt = tr.get("source"), tr.get("target")
        if src not in loc_name or tgt not in loc_name:
            warn.append(where + ": transition " + str(tr.get(XMI + "id")) + " has a source or target "
                        "outside this region and is dropped")
            continue
        tag = loc_name[src] + " -> " + loc_name[tgt]
        guard, comments = None, []
        ev = event_of(tr, by_id)
        if ev is not None and mtype(ev) == "uml:ChangeEvent":
            b = body_of(ev.find("changeExpression"))
            if b:
                variables |= variables_in(b)
                guard, bad = translate_expr(b, scale, warn, where + " guard on " + tag)
                comments += ["ChangeEvent: " + b.strip()]
            else:
                warn.append(where + ": ChangeEvent on " + tag + " has no expression, edge left unguarded")
        elif ev is not None and mtype(ev) == "uml:TimeEvent":
            tv = time_event_value(ev)
            if tv is None:
                warn.append(where + ": TimeEvent on " + tag + " has no value, edge left unguarded")
            else:
                value, relative = tv
                if relative:
                    guard = "t >= " + value
                    relative_bound.setdefault(src, []).append(int(float(value)))
                    comments += ["TimeEvent after(" + value + ")"]
                else:
                    guard = "gt >= " + value
                    comments += ["TimeEvent at absolute time " + value]
                    warn.append(where + ": TimeEvent on " + tag + " has no isRelative attribute, read as an "
                                "absolute time on the global clock gt; UPPAAL cannot bound it from above")
        elif ev is not None:
            warn.append(where + ": trigger event of type " + mtype(ev) + " on " + tag + " is not translated")

        if tr.get("name"):
            comments += ["transition label: " + tr.get("name")]
            warn.append(where + ": transition " + tag + " carries the informal label "
                        + repr(tr.get("name")) + "; only its structured trigger is translated")

        assigns = ["t = 0"] + entry_assign.get(tgt, [])
        edges.append({"source": src, "target": tgt, "guard": guard,
                      "assignment": ", ".join(assigns), "comments": comments})

    # a location whose every outgoing edge is a relative TimeEvent gets the matching invariant
    invariant = {}
    out_count = {}
    for e in edges:
        out_count[e["source"]] = out_count.get(e["source"], 0) + 1
    for sid, bounds in relative_bound.items():
        if len(bounds) == out_count.get(sid, 0):
            invariant[sid] = "t <= " + str(min(bounds))
        else:
            warn.append(where + ": " + loc_name[sid] + " mixes a relative TimeEvent with other triggers, "
                        "so no invariant is added and the timed transition may be delayed indefinitely")

    return {
        "name": name,
        "kind": "state machine",
        "source_name": sm.get("name", ""),
        "locations": [{"id": s.get(XMI + "id"), "name": loc_name[s.get(XMI + "id")],
                       "invariant": invariant.get(s.get(XMI + "id")),
                       "comment": mtype(s)} for s in states],
        "init": init_ref,
        "edges": edges,
        "declaration": "clock t;",
        "variables": variables,
        "initial_state": next((e["target"] for e in edges if e["source"] == init_ref), None),
        "entry_assign": entry_assign,
    }


# ------------------------------------------------------------------
# activities

FORKISH = {"uml:ForkNode", "uml:JoinNode"}


def activity_template(act, by_id, parent, scale, warn):
    """One uml:Activity -> one template dict (the sequential fragment; forks are flagged)."""
    name = sanitize(act.get("name", "Activity"), "Activity")
    where = "activity " + name
    nodes = act.findall("node")
    flows = act.findall("edge")

    loc_name, used = {}, set()
    for n in nodes:
        base = sanitize(n.get("name", ""), mtype(n).split(":")[-1])
        m, k = base, 2
        while m in used:
            m, k = base + "_" + str(k), k + 1
        used.add(m)
        loc_name[n.get(XMI + "id")] = m
        if mtype(n) in FORKISH:
            warn.append(where + ": " + mtype(n).split(":")[-1] + " " + m + " becomes an ordinary location, "
                        "so its branches read as a nondeterministic choice, not as concurrency")

    def resolve(ref):
        """Lift a pin (or any non-node element) to the activity node that owns it."""
        if ref in loc_name:
            return ref
        el = by_id.get(ref)
        while el is not None:
            up = parent.get(id(el))
            if up is None:
                return None
            uid = up.get(XMI + "id")
            if uid in loc_name:
                return uid
            el = up
        return None

    init = next((n.get(XMI + "id") for n in nodes if mtype(n) == "uml:InitialNode"), None)
    if init is None and nodes:
        init = nodes[0].get(XMI + "id")
        warn.append(where + ": no InitialNode, using " + loc_name[init] + " as the initial location")

    edges, variables, dropped, lifted = [], set(), 0, 0
    for f in flows:
        s, t = resolve(f.get("source")), resolve(f.get("target"))
        if s is None or t is None:
            dropped += 1
            continue
        if s != f.get("source") or t != f.get("target"):
            lifted += 1
        guard, comments = None, [mtype(f).split(":")[-1]]
        b = body_of(f.find("guard"))
        if b:
            variables |= variables_in(b)
            guard, _ = translate_expr(b, scale, warn, where + " guard on " + loc_name[s] + " -> " + loc_name[t])
            comments += ["guard: " + b.strip()]
        if s == t:
            comments += ["self loop in the source model"]
        edges.append({"source": s, "target": t, "guard": guard, "assignment": "t = 0",
                      "comments": comments})
    if dropped:
        warn.append(where + ": " + str(dropped) + " flow(s) had an endpoint outside the activity and were dropped")
    if lifted:
        warn.append(where + ": " + str(lifted) + " object flow(s) start or end on a pin and were lifted to the "
                    "owning action")

    return {
        "name": name,
        "kind": "activity",
        "source_name": act.get("name", ""),
        "locations": [{"id": n.get(XMI + "id"), "name": loc_name[n.get(XMI + "id")],
                       "invariant": None, "comment": mtype(n)} for n in nodes],
        "init": init,
        "edges": edges,
        "declaration": "clock t;",
        "variables": variables,
        "initial_state": None,
        "entry_assign": {},
    }


# ------------------------------------------------------------------
# proof obligations from requirements

ALWAYS = ["always", "at all times", "during operation", "shall not exceed", "shall never"]
GREATER = ["more than", "greater than", "exceed", "above", "at least"]
LESS = ["less than", "below", "under", "within"]
NOT_MORE = ["shall not exceed", "no more than", "at most"]
TIME_WORDS = ["second", "seconds", "minute", "minutes", "ms"]
NUMBER = re.compile(r"(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*%?")


def requirement_query(req, aliases, scale, clock="gt"):
    """Turn one requirement's Text into an UPPAAL query, if the alias table binds it.

    `aliases` maps a model variable (or the global clock name) to the phrases that stand for it
    in requirement prose.  The SysML model carries no structured satisfy/verify link between a
    requirement and a state-machine variable, so this table is what supplies it; the demo
    passes it in explicitly.
    """
    text = req["text"]
    low = text.lower()
    var = next((v for v, phrases in aliases.items()
                if any(p.lower() in low for p in phrases)
                or re.search(r"\b" + re.escape(v.lower()) + r"\b", low)), None)
    if var is None:
        return None
    m = NUMBER.search(text)
    if m is None:
        return None
    const = float(m.group(1).replace(",", ""))

    is_time = var == clock
    if any(p in low for p in NOT_MORE):
        op = "<="
    elif any(p in low for p in LESS):
        op = "<"
    elif any(p in low for p in GREATER):
        op = ">"
    else:
        return None
    value = const if is_time else int(round(const * scale))
    quant = "A[]" if any(p in low for p in ALWAYS) or op in ("<", "<=") else "A<>"
    formula = quant + " " + var + " " + op + " " + (str(int(value)) if float(value).is_integer() else str(value))
    return {"formula": formula, "comment": req["id"] + " " + req["name"] + ": " + text}


# ------------------------------------------------------------------
# UPPAAL XML

DOCTYPE = ("<!DOCTYPE nta PUBLIC '-//Uppaal Team//DTD Flat System 1.1//EN' "
           "'http://www.it.uu.se/research/group/darts/uppaal/flat-1_1.dtd'>")


def _label(parent, kind, text, x, y):
    if not text:
        return
    e = ET.SubElement(parent, "label", {"kind": kind, "x": str(x), "y": str(y)})
    e.text = text


def build_nta(templates, global_decl, queries):
    """Assemble the NTA. Location ids are the `idN` form UPPAAL writes, numbered across the
    whole network, because both UPPAAL and pyuppaal read the integer out of that name."""
    nta = ET.Element("nta")
    d = ET.SubElement(nta, "declaration")
    d.text = global_decl

    next_id = 0
    for t in templates:
        tpl = ET.SubElement(nta, "template")
        ET.SubElement(tpl, "name").text = t["name"]
        if t["declaration"]:
            ET.SubElement(tpl, "declaration").text = t["declaration"]
        uid, pos = {}, {}
        for i, loc in enumerate(t["locations"]):
            x, y = 200 * (i % 6), 200 * (i // 6)
            uid[loc["id"]] = "id" + str(next_id)
            next_id += 1
            pos[loc["id"]] = (x, y)
            e = ET.SubElement(tpl, "location", {"id": uid[loc["id"]], "x": str(x), "y": str(y)})
            ET.SubElement(e, "name", {"x": str(x - 10), "y": str(y - 34)}).text = loc["name"]
            _label(e, "invariant", loc["invariant"], x - 10, y + 20)
            if loc["comment"]:
                ET.SubElement(e, "label", {"kind": "comments", "x": str(x - 10), "y": str(y + 40)}).text = loc["comment"]
        if t["init"]:
            ET.SubElement(tpl, "init", {"ref": uid[t["init"]]})
        for e in t["edges"]:
            x = (pos[e["source"]][0] + pos[e["target"]][0]) // 2
            y = (pos[e["source"]][1] + pos[e["target"]][1]) // 2
            tr = ET.SubElement(tpl, "transition")
            ET.SubElement(tr, "source", {"ref": uid[e["source"]]})
            ET.SubElement(tr, "target", {"ref": uid[e["target"]]})
            _label(tr, "guard", e["guard"], x, y - 20)
            _label(tr, "assignment", e["assignment"], x, y)
            _label(tr, "comments", "; ".join(e["comments"]), x, y + 20)

    ET.SubElement(nta, "system").text = "\n".join(
        [t["name"].lower() + "_p = " + t["name"] + "();" for t in templates]
        + ["system " + ", ".join(t["name"].lower() + "_p" for t in templates) + ";"])

    q = ET.SubElement(nta, "queries")
    for item in queries:
        e = ET.SubElement(q, "query")
        ET.SubElement(e, "formula").text = item["formula"]
        ET.SubElement(e, "comment").text = item.get("comment", "")
    return nta


def write_nta(nta, path):
    ET.indent(nta, space="\t")
    body = ET.tostring(nta, encoding="unicode")
    with open(path, "w") as f:
        f.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + DOCTYPE + "\n" + body + "\n")
    return path


# ------------------------------------------------------------------
# the whole translation

def translate(model_path, out_path, scale=DEFAULT_SCALE, aliases=None, activities=None,
              state_machines=None, clock="gt"):
    """Read a model, translate it, write the NTA. Returns (templates, queries, warnings)."""
    root = load_model(model_path)
    by_id, parent = index_model(root)
    warn = []

    sms = elements_of_type(root, "uml:StateMachine")
    if state_machines is not None:
        sms = [s for s in sms if re.sub(r"^SMD\s+", "", s.get("name", "")) in state_machines]
    acts = elements_of_type(root, "uml:Activity")
    if activities is not None:
        acts = [a for a in acts if a.get("name", "") in activities]

    templates = [state_machine_template(s, by_id, scale, warn) for s in sms]
    for a in acts:
        if not a.findall("node"):
            warn.append("activity " + (a.get("name") or "?") + " has no nodes and is skipped")
            continue
        templates.append(activity_template(a, by_id, parent, scale, warn))

    variables = sorted(set().union(*[t["variables"] for t in templates]) if templates else [])
    decl = ["// generated by veritas/formal/sysml2uppaal from " + os.path.basename(model_path),
            "// reals are scaled to integers by " + str(scale),
            "clock " + clock + ";"]
    for v in variables:
        init = 0
        for t in templates:
            a = t["entry_assign"].get(t["initial_state"], [])
            for term in a:
                m = re.match(r"^\s*" + v + r"\s*=\s*(-?[0-9]+)\s*$", term)
                if m:
                    init = int(m.group(1))
        decl.append("int " + v + " = " + str(init) + ";")
    if variables:
        decl.append("// the model gives no initial value for these; each is set to what the entry")
        decl.append("// behaviour of the state reached from the initial pseudostate assigns, else 0")

    queries = []
    if aliases:
        for req in requirements(root):
            q = requirement_query(req, aliases, scale, clock)
            if q:
                queries.append(q)
    if templates:
        queries.append({"formula": "A[] not deadlock",
                        "comment": "structural check: no reachable state of the network blocks"})
    for t in templates:
        for loc in t["locations"]:
            queries.append({"formula": "E<> " + t["name"].lower() + "_p." + loc["name"],
                            "comment": "reachability of " + loc["name"] + " in " + t["name"]})

    nta = build_nta(templates, "\n".join(decl), queries)
    write_nta(nta, out_path)
    return templates, queries, warn


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("model", help=".mdzip or .xmi")
    p.add_argument("out", help="output UPPAAL .xml")
    p.add_argument("--scale", type=int, default=DEFAULT_SCALE)
    a = p.parse_args()
    templates, queries, warn = translate(a.model, a.out, scale=a.scale)
    print("wrote " + a.out + " with " + str(len(templates)) + " template(s) and "
          + str(len(queries)) + " queries")
    for w in warn:
        print("warning: " + w)


if __name__ == "__main__":
    main()
