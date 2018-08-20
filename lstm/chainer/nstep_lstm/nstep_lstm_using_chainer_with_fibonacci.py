#!/usr/bin/env python
# -*- coding: utf-8 -*-

from params import *  # noqa
import chainer
from chainer import optimizers
import chainer.links as L
import chainer.functions as F
import numpy as np
from chainer import serializers
import _pickle
import nstep_lstm
import sys
# https://qiita.com/aonotas/items/8e38693fb517e4e90535
# https://qiita.com/TokyoMickey/items/cc8cd43545f2656b1cbd

xp = np
if GPU >= 0:
    xp = chainer.cuda.cupy


# LSTM
class MyNet(chainer.Chain):

    def __init__(self, n_layers=1, n_in=1, n_hidden=20, n_out=1, dropout=0.5, train=True):
        super(MyNet, self).__init__()
        with self.init_scope():
            self.l1 = nstep_lstm.LSTM(n_layers, n_in, n_hidden, dropout)
            self.l2 = L.Linear(n_hidden, n_out, initialW=chainer.initializers.Normal(scale=0.01))
            self.train = train

    def __call__(self, x):
        # x.shape: [(seq_size, n_in)] * batch_size
        h = self.l1(x)  # [(seq_size, n_hidden)] * batch_size
        h = F.concat(h, axis=0)  # [seq_size * batch_size, n_hidden]
        y = self.l2(h)  # [seq_size * batch_size, n_out]
        return y

    def reset_state(self):
        self.l1.reset_state()


# 損失値計算器
class LossCalculator(chainer.Chain):

    def __init__(self, model):
        super(LossCalculator, self).__init__()
        with self.init_scope():
            self.model = model

    # x.shape: [(seq_size, n_in)] * batch_size
    # t.shape: [(seq_size, n_out)] * batch_size
    def __call__(self, x, t):
        y = self.model(x)  # [seq_size * batch_size, n_out]
        assert y.shape == (SEQUENCE_SIZE * BATCH_SIZE, N_OUT)
        t = F.concat(t, axis=0)  # [seq_size * batch_size, n_out]
        assert t.shape == (SEQUENCE_SIZE * BATCH_SIZE, N_OUT)
        loss = F.mean_squared_error(y, t)
        return loss


# バッチ単位で1つのシーケンスを学習する。
def calculate_loss(model, seq):
    batch_size, cols = seq.shape
    assert cols - 1 == SEQUENCE_SIZE
    xs = []
    ts = []
    for row in seq:
        x = row[:-1].reshape(cols - 1, N_IN)
        t = row[1:].reshape(cols - 1, N_OUT)
        assert x.shape == (SEQUENCE_SIZE, N_IN)
        assert t.shape == (SEQUENCE_SIZE, N_OUT)
        xs.append(chainer.Variable(x.astype(dtype=xp.float32)))
        ts.append(chainer.Variable(t.astype(dtype=xp.float32)))
    loss = model(xs, ts)
    return loss


# モデルを更新する。
def update_model(model, seq):
    loss = calculate_loss(model, seq)

    # 誤差逆伝播
    loss_calculator.cleargrads()
    loss.backward()

    # バッチ単位で古い記憶を削除し、計算コストを削減する。
    loss.unchain_backward()

    # バッチ単位で更新する。
    optimizer.update()
    return loss


# Fibonacci数列から周期関数を作る。
class DatasetMaker(object):

    @staticmethod
    def make(total_size, value):
        return (DatasetMaker.fibonacci(total_size) % value).astype(np.float32)

    # 全データを入力時のシーケンスに分割する。
    @staticmethod
    def make_sequences(data, seq_size):
        data_size = len(data)
        row = data_size - seq_size
        seqs = xp.ndarray((row, seq_size)).astype(xp.float32)
        for i in range(row):
            seqs[i, :] = data[i: i + seq_size]
        return seqs

    @staticmethod
    def fibonacci(size):
        values = [1, 1]
        for _ in range(size - len(values)):
            values.append(values[-1] + values[-2])
        return np.array(values)


# テストデータに対する誤差を計算する。
def evaluate(loss_calculator, seqs):
    batches = seqs.shape[0] // BATCH_SIZE
    clone = loss_calculator.copy()
    clone.train = False
    clone.model.reset_state()
    start = 0
    for i in range(batches):
        seq = seqs[start: start + BATCH_SIZE]
        start += BATCH_SIZE

        loss = calculate_loss(clone, seq)
    return loss


if __name__ == '__main__':

    # _/_/_/ データの作成

    dataset = DatasetMaker.make(TOTAL_SIZE, VALUE)
    if GPU >= 0:
        dataset = chainer.cuda.to_gpu(dataset)

    # 訓練データと検証データに分ける。
    n_train = int(TOTAL_SIZE * SPRIT_RATE)
    print('n_train', n_train)
    n_val = TOTAL_SIZE - n_train
    print('n_val', n_val)
    train_dataset = dataset[: n_train].copy()
    print('train_dataset.shape', train_dataset.shape)
    val_dataset = dataset[n_train:].copy()
    print('val_dataset.shape', val_dataset.shape)
    print('SEQUENCE_SIZE', SEQUENCE_SIZE)

    # 長さSEQUENCE_SIZE + 1の時系列データを始点を1つずつずらして作る。
    # +1は教師データ作成のため。
    train_seqs = DatasetMaker.make_sequences(train_dataset, SEQUENCE_SIZE + 1)
    val_seqs = DatasetMaker.make_sequences(val_dataset, SEQUENCE_SIZE + 1)

    # _/_/_/ モデルの設定

    mynet = MyNet(N_LAYERS, N_IN, N_HIDDEN, N_OUT, DROPOUT)
    if GPU >= 0:
        mynet.to_gpu()

    loss_calculator = LossCalculator(mynet)

    # _/_/_/ 最適化器の作成

    optimizer = optimizers.Adam()
    optimizer.setup(loss_calculator)

    # _/_/_/ 訓練

    batches = train_seqs.shape[0] // BATCH_SIZE
    print('batches: {}'.format(batches))
    losses = []
    val_losses = []
    for epoch in range(EPOCHS):
        # エポックの最初でシャッフルする。
        xp.random.shuffle(train_seqs)

        start = 0
        for i in range(batches):
            seq = train_seqs[start: start + BATCH_SIZE]
            start += BATCH_SIZE

            # バッチ単位でモデルを更新する。
            loss = update_model(loss_calculator, seq)

        # 検証する。
        val_loss = evaluate(loss_calculator, val_seqs)

        # エポック単位の表示
        average_loss = loss.data
        average_val_loss = val_loss.data
        print('epoch:{}, loss:{}, val_loss:{}'.format(epoch, average_loss, average_val_loss))

        losses.append(average_loss)
        val_losses.append(average_val_loss)

    # 保存する。
    serializers.save_npz('./chainer_mynet_dropout={}.npz'.format(DROPOUT), mynet)
    _pickle.dump(losses, open('./chainer_losses_dropout={}.pkl'.format(DROPOUT), 'wb'))
    _pickle.dump(val_losses, open('./chainer_val_losses_dropout={}.pkl'.format(DROPOUT), 'wb'))
