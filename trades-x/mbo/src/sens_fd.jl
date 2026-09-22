# Sensitivity of the coverage oracles to the sensor parameters.
#
# This file loads util_data_mod.jl rather than util_data.jl: the two differ only
# in that the modified structs declare their numeric fields `Real` instead of
# `Float64`, which is what lets ForwardDiff push dual numbers through
# `sensor_coverage_oracle` unchanged. The gradients below are therefore taken
# through the same oracle the enumeration uses, not through a rewritten copy.
#
# FiniteDifferences gives the independent check.

using FiniteDifferences
using ForwardDiff

include("util_data_mod.jl");
include("oracles.jl");

sensors = [a1, a2, a3, a4, b1, b2, b3, b4, c1, c2, c3, d1, d2]

# ------------------------------------------------------------------
# coverage as a function of the parameters that matter, one per sensor type

# lidar: max_range, v_fov
function lidar_coverage(p)
    s = lidar("vlp16", [0.0 0.0 0.0], [0.0 0.0 0.0], 15, 2 * π, p[2], 16, 1875, p[1], 10000, 80)
    return sensor_coverage_oracle(s)
end

# laser: h_fov, max_range
function laser_coverage(p)
    s = laser("lms1xx", [0.0 0.0 0.0], [0.0 0.0 -1.57], 25, p[1], 1.57, 0.1, p[2], 1000, 30)
    return sensor_coverage_oracle(s)
end

# depth camera: max_range, h_fov, v_fov
function depth_camera_coverage(p)
    s = depth_camera("d455", [0.0 0.0 0.0], [0.0 0.0 0.0], 1920, 1080, 15, p[2], p[3], p[1], 3000, 10)
    return sensor_coverage_oracle(s)
end

# RGB camera: max_range, h_fov (v_fov is fixed at 1.273 inside the oracle)
function camera_coverage(p)
    s = camera("blackfly", [0.0 0.0 0.0], [0.0 0.0 0.0], 720, 540, 30, p[2], 0.5, p[1], 1500, 3)
    return sensor_coverage_oracle(s)
end

# ------------------------------------------------------------------
# gradients, catalogue values as the operating point

fdm = central_fdm(5, 1)

function report(name, f, p, names)
    ad = ForwardDiff.gradient(f, p)
    fd = grad(fdm, f, p)[1]
    println(name, " coverage = ", round(f(p), digits=6), " m^3")
    for i in eachindex(p)
        println("  d/d", names[i], "  forwarddiff ", round(ad[i], digits=6),
                "  finitediff ", round(fd[i], digits=6))
    end
    println("  max abs AD - FD: ", maximum(abs.(ad .- fd)))
    return ad
end

g_lidar = report("lidar VLP-16", lidar_coverage, [100.0, 0.526], ["max_range", "v_fov"])
g_laser = report("laser LMS1xx", laser_coverage, [4.71, 20.0], ["h_fov", "max_range"])
g_depth = report("depth camera D455", depth_camera_coverage, [6.0, 1.501, 0.9948],
                 ["max_range", "h_fov", "v_fov"])
g_camera = report("RGB camera Blackfly-A", camera_coverage, [50.0, 1.047],
                  ["max_range", "h_fov"])

# ------------------------------------------------------------------
# requirement-sensitivity ranking
#
# The relative sensitivity p * df/dp says how much coverage moves for a one
# percent move in the parameter, which is what makes the four comparable.

entries = []
for (name, g, p, names) in [("lidar VLP-16", g_lidar, [100.0, 0.526], ["max_range", "v_fov"]),
                            ("laser LMS1xx", g_laser, [4.71, 20.0], ["h_fov", "max_range"]),
                            ("depth camera D455", g_depth, [6.0, 1.501, 0.9948], ["max_range", "h_fov", "v_fov"]),
                            ("RGB camera Blackfly-A", g_camera, [50.0, 1.047], ["max_range", "h_fov"])]
    for i in eachindex(p)
        push!(entries, (name * " " * names[i], p[i] * g[i]))
    end
end
sort!(entries, by=e -> -abs(e[2]))

println()
println("parameters ranked by relative sensitivity p * dcoverage/dp [m^3]")
for e in entries
    println("  ", e[1], "  ", round(e[2], digits=3))
end
