"""Check UPPAAL models with `verifyta` and write a verdict report.

Both generators in `formal/` write a model whose `<queries>` block carries the proof
obligations: `sysml2uppaal` turns SysML requirements into them, `bt2automata` writes the two
reachability queries of the behavior tree.  This is the driver that runs them.

    uv run python formal/verify.py formal/sysml2uppaal/battery_sm.xml \
                                   formal/bt2automata/BT_converted.xml

What it does, per model:

1. reads the `<queries>` block and writes a sibling `.q` file -- one formula per line, each
   query's comment above it as `//` lines.  The flat-system 1.1 DTD both models declare has
   no `<queries>` element, so the queries live inside the model as a convenience for the
   UPPAAL GUI; handing `verifyta` a separate query file is the form every version accepts;
2. locates `verifyta`: `--verifyta`, then `$UPPAAL_HOME/bin-Linux/verifyta`, then
   `$UPPAAL_HOME/bin/verifyta`, then `PATH`;
3. runs `verifyta -t0 MODEL QUERIES`.  `-t0` is the `--diagnostic` option with argument 0,
   "some trace", so a failing query comes back with a counter-example rather than a bare no;
   no other flag is passed, because the rest of the option set differs between versions.
   UPPAAL 5.x also reads the model's own `<queries>` block, and `--embedded-queries` asks for
   that instead of the extracted file;
4. parses the per-query verdict lines and writes `verification_report.json` and
   `verification_report.md`, both carrying the version string `verifyta -v` printed.

Exit status: 0 when every query came back with a verdict (whatever the verdict), 1 when a
model could not be checked, 2 when no `verifyta` was found.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

# `Verifying formula 1 at /nta/queries/query[1]/formula`, which verifyta prints before each
# verdict; 5.x says "property" in some builds, so both words are accepted.
INDEX_LINE = re.compile(r"^\s*Verifying\s+(?:formula|property)\s+(\d+)\b", re.IGNORECASE)

# `-- Formula is satisfied.` / `-- Formula is NOT satisfied.` / `-- Formula MAY be satisfied.`
# The NOT alternative comes first: alternation is leftmost-first and `is` would swallow it.
VERDICT_LINE = re.compile(
    r"^\s*--\s*(?:Formula|Property)\s+(is\s+NOT|MAY\s+be|is)\s+satisfied", re.IGNORECASE)

VERDICTS = {"is": "satisfied", "is not": "not satisfied", "may be": "may be satisfied"}

# 5.x writes an erase-line escape before the verdict line while its progress indicator runs
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def read_queries(model_path):
    """The model's `<queries>` block as [{index, formula, comment}], 1-based as verifyta counts."""
    nta = ET.parse(model_path).getroot()
    block = nta.find("queries")
    out = []
    for i, q in enumerate(block.findall("query") if block is not None else [], start=1):
        formula = q.find("formula")
        comment = q.find("comment")
        out.append({
            "index": i,
            "formula": (formula.text or "").strip() if formula is not None else "",
            "comment": (comment.text or "").strip() if comment is not None else "",
        })
    return out


def write_query_file(queries, path):
    """Write the queries as a `.q` file: each comment as `//` lines, then the formula."""
    lines = []
    for q in queries:
        for line in q["comment"].splitlines():
            lines.append("// " + line.strip())
        lines.append(q["formula"])
    open(path, "w").write("\n".join(lines) + "\n")
    return path


def find_verifyta(explicit=None):
    """`--verifyta`, then `$UPPAAL_HOME/bin-Linux/verifyta`, then `$UPPAAL_HOME/bin/verifyta`,
    then `PATH`. Returns the path or None."""
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return os.path.abspath(explicit)
        return shutil.which(explicit)
    home = os.environ.get("UPPAAL_HOME")
    if home:
        for rel in ("bin-Linux/verifyta", "bin/verifyta"):
            p = os.path.join(home, rel)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return shutil.which("verifyta")


def parse_verdicts(text):
    """Pull [(query index, verdict)] out of verifyta's output.

    verifyta writes the verdicts in query-file order; the `Verifying formula N` line gives the
    index directly when it is present, and the position in the output is used when it is not.
    """
    out = []
    index = None
    for line in ANSI.sub("", text).splitlines():
        m = INDEX_LINE.match(line)
        if m:
            index = int(m.group(1))
            continue
        m = VERDICT_LINE.match(line)
        if m:
            key = " ".join(m.group(1).split()).lower()
            out.append((index if index is not None else len(out) + 1, VERDICTS[key]))
            index = None
    return out


def verifyta_version(verifyta):
    """The first line of `verifyta -v`, which names the version."""
    r = subprocess.run([verifyta, "-v"], capture_output=True, text=True)
    text = ANSI.sub("", (r.stdout or "") + (r.stderr or "")).strip()
    return text.splitlines()[0] if text else "unknown"


def check_model(verifyta, model_path, query_path=None, timeout=600, embedded=False):
    """Run verifyta on one model and attach a verdict to every query of that model."""
    queries = read_queries(model_path)
    if query_path is None:
        query_path = os.path.splitext(model_path)[0] + ".q"
    write_query_file(queries, query_path)

    cmd = [verifyta, "-t0", model_path] + ([] if embedded else [query_path])
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    seconds = time.perf_counter() - t0
    output = (r.stdout or "") + (r.stderr or "")

    verdicts = dict(parse_verdicts(output))
    for q in queries:
        q["verdict"] = verdicts.get(q["index"], "no verdict")
    return {
        "model": model_path,
        "query_file": query_path,
        "command": " ".join(cmd),
        "returncode": r.returncode,
        "seconds": seconds,
        "queries": queries,
        "output": output,
    }


def write_report(results, verifyta, version, out_dir):
    """Write `verification_report.json` and `verification_report.md` into `out_dir`."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    doc = {"generated": stamp, "verifyta": verifyta, "version": version, "models": results}
    json_path = os.path.join(out_dir, "verification_report.json")
    open(json_path, "w").write(json.dumps(doc, indent=2) + "\n")

    lines = ["# UPPAAL verification report", "",
             version, "generated: " + stamp, ""]
    for res in results:
        lines += ["## " + os.path.basename(res["model"]), "",
                  "queries: `" + os.path.basename(res["query_file"]) + "`, "
                  + str(round(res["seconds"], 2)) + " s, exit " + str(res["returncode"]), "",
                  "| # | formula | requirement / comment | verdict |",
                  "|---|---|---|---|"]
        for q in res["queries"]:
            comment = " ".join(q["comment"].split()) or "-"
            lines.append("| " + str(q["index"]) + " | `" + q["formula"] + "` | "
                         + comment + " | " + q["verdict"] + " |")
        lines.append("")
    md_path = os.path.join(out_dir, "verification_report.md")
    open(md_path, "w").write("\n".join(lines))
    return json_path, md_path


def main():
    p = argparse.ArgumentParser(description="check UPPAAL models with verifyta")
    p.add_argument("models", nargs="+", help="UPPAAL .xml model files")
    p.add_argument("--verifyta", help="path to the verifyta binary")
    p.add_argument("--out", default=".", help="directory for the report files")
    p.add_argument("--timeout", type=float, default=600.0, help="seconds per model")
    p.add_argument("--embedded-queries", action="store_true",
                   help="let verifyta read the model's own <queries> block (UPPAAL 5.x)")
    a = p.parse_args()

    verifyta = find_verifyta(a.verifyta)
    if verifyta is None:
        print("set UPPAAL_HOME to an UPPAAL installation, or pass --verifyta "
              "<path to verifyta>")
        return 2

    version = verifyta_version(verifyta)
    print(version)
    results = [check_model(verifyta, m, timeout=a.timeout, embedded=a.embedded_queries)
               for m in a.models]
    json_path, md_path = write_report(results, verifyta, version, a.out)

    failed = False
    for res in results:
        print(os.path.basename(res["model"]) + "  " + str(len(res["queries"])) + " queries, "
              + str(round(res["seconds"], 2)) + " s")
        for q in res["queries"]:
            print("  " + q["formula"] + "  ->  " + q["verdict"])
            failed |= q["verdict"] == "no verdict"
        if res["returncode"] != 0 and not res["queries"]:
            failed = True
    print("wrote " + json_path)
    print("wrote " + md_path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
