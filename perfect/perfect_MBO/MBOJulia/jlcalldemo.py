from juliacall import Main as jl 
from juliacall import Pkg as pkg


# Test basic functionality of calling Julia:
jl.println("Hello from Julia!")

# Activate and instantiate the julia env where the .toml files live
pkg.activate(".")

# Uncomment this line for the first run to install the dependencies.

# pkg.instantiate()

# Now run the src/mbo.jl script- should return the outputs
jl.include("src/mbo.jl")

print("Done!")