#!/usr/bin/env python
# -*- coding:utf-8 -*-
import parameters as pa
import qs_updater as qs
import qpi_updater as qp
import qmu_updater as qm
import qlambda_updater as ql
import torch
import torch.distributions as D
import matplotlib.pyplot as plt
import numpy as np
# import random


DIM = 2
K = 3
NU = DIM * torch.ones(K)
MAX_ITER = 1000
OBS_NUM = 1000
# SEED = 1
EPSILON = 1.0e-5
CENTERS = torch.tensor([
    [-10.0, 0.0],
    [10.0, 0.0],
    [0.0, 10.0]])


# torch.manual_seed(SEED)
# random.seed(SEED)
# np.random.seed(SEED)


def display_graph(dataset):
    xs = []
    ys = []
    for (x, y) in dataset.numpy():
        xs.append(x)
        ys.append(y)
    plt.scatter(xs, ys, marker='.')
    plt.savefig('./dataset.jpg')
    return ((np.min(xs), np.max(xs)), (np.min(ys), np.max(ys)))


LABELS = {0: "red", 1: "green", 2: "blue"}


# eta:(N,K), dataset:(N,D)
def save_results(eta, dataset):
    red = np.array([1, 0, 0])
    green = np.array([0, 1, 0])
    blue = np.array([0, 0, 1])

    colors = []
    for indices in eta:
        c = red * indices[0].numpy() + green * indices[1].numpy() + blue * indices[2].numpy()
        colors.append(c)

    plt.scatter(dataset[:, 0], dataset[:, 1], marker='.', c=colors)
    plt.savefig('./results.jpg')


def make_dataset(obs_num, dim):
    loc_0 = CENTERS[0]
    cov_0 = torch.eye(dim) * 2.0
    dis_0 = D.MultivariateNormal(loc=loc_0, covariance_matrix=cov_0)

    loc_1 = CENTERS[1]
    cov_1 = torch.eye(dim) * 2.0
    dis_1 = D.MultivariateNormal(loc=loc_1, covariance_matrix=cov_1)

    loc_2 = CENTERS[2]
    cov_2 = torch.eye(dim) * 2.0
    dis_2 = D.MultivariateNormal(loc=loc_2, covariance_matrix=cov_2)

    values = []
    for _ in range(OBS_NUM // K):
        a = dis_0.sample()
        b = dis_1.sample()
        c = dis_2.sample()
        values.append(a)
        values.append(b)
        values.append(c)
    return torch.stack(values, dim=0)


def check(dataset):
    std, mean = torch.std_mean(dataset, dim=0)
    print(std)
    print(mean)


if __name__ == "__main__":
    try:
        hyper_params = pa.HyperParameters(dim=DIM, k=K, nu=NU)
        qs_updater = qs.QsUpdater()
        qp_updater = qp.QpiUpdater(hyper_params)
        qm_updater = qm.QmuUpdater(hyper_params)
        ql_updater = ql.QlambdaUpdater(hyper_params)
        dataset = make_dataset(OBS_NUM, DIM)
        std, mean = torch.std_mean(dataset, dim=0)
        dataset = (dataset - mean) / std
        (x_range, y_range) = display_graph(dataset)

        cxs = np.random.uniform(x_range[0], x_range[1], K)
        cys = np.random.uniform(y_range[0], y_range[1], K)
        cs = []
        for (cx, cy) in zip(cxs, cys):
            cs.append([cx, cy])
        # initialize mu
        qm_updater.m = torch.tensor(cs).float()
        # print("initial m ", qm_updater.m)

        prev_m = qm_updater.m.clone()
        for i in range(MAX_ITER):
            qs_updater.update(
                dataset,
                ql_updater.W,
                ql_updater.nu,
                qm_updater.m,
                qm_updater.beta,
                qp_updater.alpha)
            ql_updater.update(dataset, qs_updater.eta, qm_updater.beta, qm_updater.m)
            qm_updater.update(dataset, qs_updater.eta)
            qp_updater.update(dataset, qs_updater.eta)
            diff_m = torch.max(torch.abs(qm_updater.m - prev_m))
            if diff_m < EPSILON:
                print("diff is {} at {}".format(diff_m, i))
                break
            prev_m = qm_updater.m.clone()
        print("final m ")
        for m in qm_updater.m * std + mean:
            print(m.tolist())
        save_results(qs_updater.eta, dataset)

    except Exception as e:
        print("Exception: {}".format(e))
