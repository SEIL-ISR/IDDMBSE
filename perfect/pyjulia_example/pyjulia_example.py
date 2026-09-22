import json

from julia.api import Julia
jl = Julia(compiled_modules=False)

from julia import Main


Main.include("fake_mbo.jl")

indexed_designs = json.load(open("designs.json", "r"))

n_designs = Main.fake_mbo(indexed_designs)
assert n_designs == len(indexed_designs)
print("Python calls this a success!")
