# PyJulia call-through example

Reference only. A minimal example of calling the Julia MBO stage from Python:
`pyjulia_example.py` starts Julia through PyJulia, runs `fake_mbo.jl` (which
just counts the designs in `designs.json`) and reads the answer back. It shows
the call mechanism, not the real optimization.

Moved here from `perfect/pyjulia_example/` on 2026-09-22, unchanged. The
`juliacall` route, which is what `../mbo/JuliaCall_README.md` describes, is the
newer one.
