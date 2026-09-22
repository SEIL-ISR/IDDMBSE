#!/usr/bin/env python3
"""A stand-in for `verifyta` that writes the same shape of output, for the tests.

It takes the same command line -- `[options] MODEL QUERY` -- reads the formulas out of the
query file, and prints one `Verifying formula N ...` line and one verdict line per formula, so
`formal/verify.py` can be exercised end to end without an UPPAAL installation.  It decides
verdicts by a trivial rule and checks nothing:

* a formula containing `not deadlock` is satisfied;
* a formula containing `gt < 180` is NOT satisfied;
* a formula beginning with `A<>` MAY be satisfied;
* anything else is satisfied.

`-v` prints a version line containing the word UPPAAL, which is how pyuppaal and this repo's
driver recognise a verifyta.
"""

import sys


def verdict(formula):
    if "not deadlock" in formula:
        return "is satisfied"
    if "gt < 180" in formula:
        return "is NOT satisfied"
    if formula.startswith("A<>"):
        return "MAY be satisfied"
    return "is satisfied"


def main(argv):
    if "-v" in argv or "--version" in argv:
        print("UPPAAL 4.1.26 (rev. fake), fake_verifyta stub")
        return 0
    paths = [a for a in argv if not a.startswith("-")]
    if len(paths) < 2:
        print("Usage: verifyta [OPTION]... MODEL QUERY", file=sys.stderr)
        return 1
    model, query_file = paths[0], paths[1]
    formulas = [line.strip() for line in open(query_file)
                if line.strip() and not line.strip().startswith("//")]

    print("Options for the verification:")
    print("  Generating some trace")
    print("  Search order is breadth first")
    print("Verifying " + model)
    for i, f in enumerate(formulas, start=1):
        print()
        print("Verifying formula " + str(i) + " at /nta/queries/query[" + str(i) + "]/formula")
        print(" -- Formula " + verdict(f) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
