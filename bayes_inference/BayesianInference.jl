#!/usr/bin/env julia

include("Utils.jl")
include("DatasetMaker.jl")
include("Params.jl")

import DatasetMaker
import Utils
import Params


function draw_uncertainty(oxs, oys, sigmas, n, color)
    upper_bounds = oys + n * sigmas
    lower_bounds = oys - n * sigmas
    PyPlot.fill_between(oxs, lower_bounds, upper_bounds, alpha=0.3, label="[-$(n)σ,+$(n)σ]", facecolor=color)
end


function draw_curves(oxs, oys, oys_ground_truth, xs, ys, sigmas)
    PyPlot.title("Bayesian Inference")
 
    # draw predictive curve
    PyPlot.plot(oxs, oys, label="predictive curve", linestyle="dashed")
   
    # draw original curve
    PyPlot.plot(oxs, oys_ground_truth, label="original curve")
    
    # draw observed dataset
    PyPlot.scatter(xs, ys, label="observed dataset")

    # draw uncertainties
    draw_uncertainty(oxs, oys, sigmas, 3, "red")
    draw_uncertainty(oxs, oys, sigmas, 2, "yellow")
    draw_uncertainty(oxs, oys, sigmas, 1, "green")

    PyPlot.legend(loc="best")
    PyPlot.savefig("bayes.png")
    PyPlot.show()
end


function main()
    # generate observed dataset
    xs, ys = DatasetMaker.make_observed_dataset(Params.RANGE, Params.N_SAMPLES)
    # DatasetMaker.save_dataset(xs, ys, "./dataset.txt")

    # extend xs(vector) to matrix 
    xs_matrix = Utils.make_input_matrix(xs, Params.M)

    # solve a problem by bayesian inference 
    s, w = Utils.make_solution(xs_matrix, ys, Params.M)

    # predict curve for oxs
    oxs = linspace(0, Params.RANGE, Params.N_STEPS)
    oxs_matrix = Utils.make_input_matrix(oxs, Params.M)
    oys = oxs_matrix * w

    # make original curve for oxs
    oys_ground_truth = DatasetMaker.original_curve.(oxs)

    # calculate sigma by bayesian inference
    sigmas = sqrt.(Utils.calculate_inv_lambda_in_bayesian(s, oxs, Params.M))

    # draw curves
    draw_curves(oxs, oys, oys_ground_truth, xs, ys, sigmas)
end


main()
