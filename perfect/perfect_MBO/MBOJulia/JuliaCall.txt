Instructtions to get Julia be called from a Python kernel of a Conda env:

1. Uninstall the pyjulia package and any related stuff from the perfect env
2. install the juliacall python package:

	python -m pip install juliacall

3. Start up python within the perfect env and run the jlcalldemo.py to just run the mbo.jl script inside /src/
4. Alternately, use the following commands if using python in the terminal:


# Import the Main module
# the below command should automatically fetch and install a julia exectuable of the latest major release using Juliaup (1.10)###
from juliacall import Main as jl 


# Import the Pkg module of Julia that's used to activate and instantiate the julia env
from juliacall import Pkg as pkg

# Test basic functionality of calling Julia:
jl.println("Hello from Julia!")

# Activate and instantiate the julia env where the .toml files live
pkg.activate(".")
pkg.instantiate()

# Now run the src/mbo.jl script- should return the outputs
jl.include("src/mbo.jl")