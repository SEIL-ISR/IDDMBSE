# plotting and parsing utilities
using Plots

#Plots.scatter(data1, data2, data3, markersize=1, color=:blue, xlabel="Cost", ylabel="RAM", zlabel="Power", title="Cost vs RAM vs Power")


using CSV
using DataFrames

par_eval =CSV.read("pareto_design_evals.csv", DataFrame)

par_val = DataFrame(par_eval, [:Cost, :RAM, :Power, :Coverage])

par_ids= CSV.read("pareto_designs.csv", DataFrame)

par_id = DataFrame(par_ids, [:DesignID])


#= argmin(par_eval[:, 4])
argmin(par_eval[:, 3])
argmin(par_eval[:, 2])
argmin(par_eval[:, 1]) =#







Plots.scatter(data1, data2, data3, markersize=data4 / mean(data4), color=:blue, xlabel="Cost", ylabel="RAM", zlabel="Power", label="Designs", title="Cost vs RAM vs Power vs Coverage")


#= using VegaLite
df = DataFrame(data_col, [:Cost, :RAM, :Power, :Coverage])
 =#
#df |> @vlplot(:point, x = :Cost, y = :RAM, z= :Power, color = {:Coverage, scale = {scheme = :plasma}})

des_id, des_cost, des_ram, des_pow, des_cov = one_design_eval(vec(Bool[0 0 0 0 0 0 0 0 0 0 1 0 0]))
Plots.scatter([des_cost], [des_ram], [des_pow], markersize=20000 * des_cov / median(par_val.Coverage), color=:red)

Plots.scatter(2,3,4)

demo_des = Bool[1 0 0 0 0 1 0 0 0 1 0 1 0;
            0 0 0 1 0 0 0 1 0 0 1 0 1;
            0 1 0 0 0 1 0 0 0 1 0 0 1;
            0 0 0 1 0 0 0 0 0 0 0 0 0;
            1 0 0 0 1 0 0 0 1 0 0 1 0;
            0 0 0 1 1 0 0 0 1 0 0 0 1;
            0 0 0 0 0 0 0 0 0 0 1 0 0]
demo_des_results= zeros(7,4)
for i in 1:7
    inst = 0
    inst, demo_des_results[i, 1], demo_des_results[i, 2], demo_des_results[i, 3], demo_des_results[i, 4] = one_design_eval(demo_des[i, :])
end


p9 = Plots.scatter(par_val.Cost, par_val.RAM, par_val.Power, markersize=4 * par_val.Coverage / median(par_val.Coverage), color=:blue, xlabel="Cost", ylabel="RAM", zlabel="Power", label="Pareto Optimal Designs", title="Cost vs RAM vs Power vs Coverage")
Plots.scatter!(demo_des_results[:, 1], demo_des_results[:, 2], demo_des_results[:, 3], markersize=4 * demo_des_results[:, 4] / median(demo_des_results[:, 4]), color=:orange, alpha=0.9, xlabel="Cost", ylabel="RAM", zlabel="Power", label="Approximate Pareto Frontier Designs", title="Cost vs RAM vs Power vs Coverage")




anim = @animate for i in 1:length(par_val.Cost)
    Plots.scatter(par_val.Cost[1:i], par_val.RAM[1:i], par_val.Power[1:i], markersize= 4 * par_val.Coverage[1:i] / median(par_val.Coverage),  alpha=1 - (i / 300), color=:blue, xlabel="Cost", ylabel="RAM", zlabel="Power", label="Pareto Optimal Designs", title="Cost vs RAM vs Power vs Coverage")
end

gif(anim, "pareto_optimal_designs.gif", fps = 10) 


cost_min = minimum(par_val.Cost)
cost_max = maximum(par_val.Cost)

ram_min = minimum(par_val.RAM)
ram_max = maximum(par_val.RAM)

power_min = minimum(par_val.Power)
power_max = maximum(par_val.Power)

anim2 = @animate for k in 1:7
    Plots.scatter([demo_des_results[(1:k), 1]], [demo_des_results[(1:k), 2]], [demo_des_results[(1:k), 3]], markersize=8, alpha=1 - (k / 7) / 5, xlim=(cost_min, cost_max), ylim=(ram_min, ram_max), zlim=(power_min, power_max), color=:red)
end

gif(anim2, "mosmo_approx_pareto.gif", fps=1)
