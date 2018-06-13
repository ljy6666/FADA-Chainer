import os
import glob
import argparse
import random

dataset_path = os.getenv('DATASET_PATH')
output_path = os.getenv('OUTPUT_PATH')


import numpy as np

import chainer
from chainer import cuda, Function, gradient_check, report, training, utils, Variable
from chainer import datasets, iterators, optimizers, serializers
from chainer.training import extensions
import chainer.links as L
import chainer.functions as F
from dataset import *
from updater import FADAUpdater

from model import *


def v(x):
    return Variable(np.asarray(x, dtype=np.float32))

def vi(x):
    return Variable(np.asarray(x, dtype=np.int32))


class Concat(chainer.Chain):
    def __init__(self, g, h):
        super(Concat, self).__init__()
        self.g = g
        self.h = h

    def __call__(self, x):
        return self.h(self.g(x))


def main(a):
    print('GPU: {}'.format(args.gpu))

    print('pretraining...')
    # Set up a neural network to train
    # g = VGGFeature(pretrain=True)
    g = VGG()
    gcl = L.Classifier(g)
    dcd = DCDNet()

    if args.gpu >= 0:
        chainer.backends.cuda.get_device_from_id(args.gpu).use()  # Make a specified GPU current
        g.to_gpu(args.gpu)  # Copy the models to the GPU
        gcl.to_gpu(args.gpu)  # Copy the models to the GPU
        dcd.to_gpu(args.gpu)

    # Setup an optimizer
    def make_optimizer(model, alpha=0.0002, beta1=0.5):
        optimizer = chainer.optimizers.Adam(alpha=alpha, beta1=beta1)
        optimizer.setup(model)
        optimizer.add_hook(chainer.optimizer.WeightDecay(0.00001), 'hook_dec')
        return optimizer

    opt_gcl = make_optimizer(gcl)
    opt_dcd = make_optimizer(dcd)

    # pretrain
    train, test = get_mnist(ndim=3)
    train_iter = chainer.iterators.SerialIterator(train, 32)
    test_iter = chainer.iterators.SerialIterator(test, args.batchsize,
                                                 repeat=False, shuffle=False)
    updater = training.StandardUpdater(train_iter, opt_gcl, device=a.gpu)

    trainer = training.Trainer(updater, (100, 'epoch'), out=a.output_path)
    trainer.extend(extensions.LogReport())
    trainer.extend(extensions.Evaluator(test_iter, g, device=args.gpu))
    trainer.extend(extensions.PrintReport([
        'epoch', 'iteration', 'main/loss', 'main/accuracy','validation/main/loss', 'validation/main/accuracy', 'elapsed_time'
    ]))
    trainer.extend(
        extensions.snapshot(
        filename='snapshot_g'),
        trigger=(100, 'epoch')
    )
    trainer.extend(extensions.ProgressBar())

    g_path = os.path.join(a.output_path, 'g.npz')
    if os.path.exists(g_path):
        ans = input('g.npz detected. Do you want to load it? [y/n]')
        if ans == 'y':
            serializers.load_npz(g_path, g)
        else:
            trainer.run()
            serializers.save_npz(g_path, g)
    else:
        trainer.run()
        serializers.save_npz(g_path, g)

    ######################################################################
    print('Train')
    print('# Minibatch-size: {}'.format(args.batchsize))
    print('# epoch: {}'.format(args.epoch))
    print('')

    opt_g = make_optimizer(g)
    train_set = MNISTSVHNDataset2()

    train_iter = chainer.iterators.SerialIterator(train_set, args.batchsize)
    # test_iter = chainer.iterators.SerialIterator(test_set, args.batchsize)

    # Set up a trainer
    updater = FADAUpdater(
        models=(g, dcd),
        iterator={
            'main': train_iter,
            # 'test': test_iter,
        },
        optimizer={
            'g': opt_g,
            'dcd': opt_dcd},
        device=args.gpu)

    trainer = training.Trainer(updater, (args.epoch, 'epoch'), out=args.output_path)

    snapshot_interval = (10, 'epoch')
    outimage_interval = (10, 'epoch')

    trainer.extend(extensions.snapshot(
        filename='snapshot'),
                   trigger=snapshot_interval)
    trainer.extend(extensions.snapshot_object(
        g, 'g_iter_{.updater.epoch}.npz'), trigger=snapshot_interval)
    trainer.extend(extensions.snapshot_object(
        dcd, 'dcd_iter_{.updater.epoch}.npz'), trigger=snapshot_interval)
    trainer.extend(extensions.LogReport())
    trainer.extend(extensions.PrintReport([
        'epoch', 'iteration', 'g/loss', 'g/acc_s', 'g/acc_t', 'dcd/loss', 'dcd/acc', 'elapsed_time'
    ]))
    # trainer.extend(extensions.ProgressBar(update_interval=10))

    if args.resume:
        # Resume from a snapshot
        chainer.serializers.load_npz(args.resume, trainer)

    # Run the training
    trainer.run()


if __name__ == '__main__':
    p = argparse.ArgumentParser()

    # dataset io
    p.add_argument('-o', '--output_path', metavar='PATH', type=str, default='test',
                   help='output_path (default: ./output)')
    # p.add_argument('-d', '--dataset', type=str, default='CS',
    #                help='MSRC or DSD or CS')
    # p.add_argument('-m', '--model', type=str, default='U',
    #                help='U or Refine')

    # train
    p.add_argument('-b', '--batchsize', metavar='N', type=int, default=1,
                   help='batch size (default: 128)')
    p.add_argument('-w', '--weight_decay', metavar='N', type=float, default=0.0001,
                   help='weight decay coefficient (default 0.00001)')
    p.add_argument('-e', '--epoch', metavar='N', type=int, default=100,
                   help='number of epochs (default: 100)')
    p.add_argument('-g', '--gpu', metavar='N', type=int, default=0,
                   help='gpu id (-1 if use cpu)')
    p.add_argument('-r', '--resume', dest='resume', action='store_true')

    args = p.parse_args()
    print('dataset_path: ', dataset_path)
    print('output_path: ', output_path)
    args.output_path = os.path.join(output_path, args.output_path)
    os.makedirs(args.output_path, exist_ok=True)

    main(args)