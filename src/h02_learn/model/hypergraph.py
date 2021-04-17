from .modules import Item
import torch
import torch.nn as nn

from utils import constants
import numpy as np
from collections import defaultdict


class Hypergraph(object):

    def __init__(self, n, chart, mlp, sentence):
        self.n = n
        self.chart = chart

        self.mlp = mlp
        self.spans = []
        self.scores = {}

        self.bucket = defaultdict(lambda: 0)

        for word in sentence:
            self.spans.append(word.clone())

    def subtrees_(self, item):
        i, j, h = item.i, item.j, item.h
        for k in range(i, j):
            for r in range(i, j):

                if (i, k, r) in self.chart:
                    item_l = self.chart[(k, i, r)]
                    item.subtrees[item_l] = item_l
                if (j, k, r) in self.chart:
                    item_r = self.chart[(j, k, r)]
                    item.subtrees[item_r] = item_r

        return item

    def arc(self, item):
        i, j, h = item.i, item.j, item.h
        # print((i,j,h))
        if i + 1 == j:
            if i == h:
                item.arcs.append((h, j))
            else:
                item.arcs.append((h, i))
        else:
            if item.l.h == h:
                item.arcs = item.l.arcs + item.r.arcs + [(h, item.r.h)]
            else:
                item.arcs = item.l.arcs + item.r.arcs + [(h, item.l.h)]

        return item

    def traverse_up(self, item_l, item_r, path):
        path.append(item_l)
        path.append(item_r)
        if not self.is_axiom(item_l):
            path = self.traverse_up(item_l.l, item_l.r, path)
        if not self.is_axiom(item_r):
            path = self.traverse_up(item_r.l, item_r.r, path)

        return path

    def easy_first_path(self):
        for item in self.chart:
            i, j, h = item.i, item.j, item.h
        pass

    def check_laplacian(self, L):
        return torch.all(torch.diag(L) >= 0.0) and torch.all(L - torch.diag(L) <= 0.0)

    def partition(self):
        # G = complete graph on self.n
        A = torch.exp(self.W)
        A = A - torch.diag(A)
        col_sum = torch.diag(torch.sum(A, dim=0))
        L = -1 * A + col_sum
        # A = torch.exp(A)
        # A = torch.narrow(A, 0, 0, self.n)
        # A = torch.narrow(A,-1,0,self.n)
        # B = A * (1 - torch.eye(self.n+1, self.n+1))
        # col_sum = torch.diag(torch.sum(B, dim=-1))
        # L = col_sum - A
        indices = list(range(self.n + 1))
        indices.remove(1)
        L = L[indices, :]
        L = L[:, indices]
        print(L)
        # L = torch.narrow(L,0,1,self.n)
        # L = torch.narrow(L,-1,1,self.n)
        print("XUYUYUYUYUYU {}".format(self.check_laplacian(L)))

        # L[0, :] = r[:-1]
        Z = L.det()
        return Z

    def probability(self, heads):
        heads_proper = [0] + heads.tolist()

        sentence_proper = list(range(len(heads_proper)))
        word2head = {w: h for (w, h) in zip(sentence_proper, heads_proper)}
        arcs = []
        for word in word2head:
            arcs.append((word2head[word], word))
        psum = 0
        for (u, v) in arcs:
            if u == 0:
                root = v
                continue
            psum += self.W[u, v]
        root_selection = self.W[root, :]
        psum = torch.exp(torch.sum(torch.tensor(psum).to(device=constants.device)))
        Z = self.partition()
        return psum / Z  # self.partition(root_selection)

    def best_path(self):
        for item in self.chart:
            # print(item)
            if item[0] == 0 and item[1] == self.n:
                goal = (0, self.n, item[2])
                break

        goal_item = self.chart[goal]
        arcs = []
        scores = torch.zeros(self.n)
        path = [goal_item]

        path = self.traverse_up(goal_item.l, goal_item.r, path)
        # print(path)
        arcs = set(goal_item.arcs)
        path_arcs = set([])
        for item in path:
            if item != goal_item:
                path_arcs = path_arcs.union(set(item.arcs))

        #print(path_arcs)
        #print(arcs)

        arcs = arcs.intersection(path_arcs)
        # do in order

        # scores = [self.chart[item].w for item in reversed(path)]
        # print(scores)

        # tot_sum = sum(scores)
        # cumsum = torch.cumsum(torch.tensor(scores), dim=-1)
        # probs = cumsum  # /tot_sum

        arcs = set(arcs)
        heads = torch.zeros(self.n)
        for (u, v) in arcs:
            heads[v - 1] = u
        return heads

    def siblings(self):
        pass

    def grandchild(self):
        pass

    def axiom(self, i):
        pass

    def is_axiom(self, item):
        pass


class LazyArcStandard(Hypergraph):

    def __init__(self, n, chart, mlp, sentence):
        super().__init__(n, chart, mlp, sentence)

    def axiom(self, i):
        return i, i + 1, i

    def is_axiom(self, item):
        i, j, h = item.i, item.j, item.h
        if j == i + 1 and i == h and j == h + 1:
            return True
        else:
            return False

    def update_chart(self, item):
        self.chart[item] = item
        return self

    def delete_from_chart(self, item):
        self.chart.chart.pop(item,None)
        return self

    def add_bucket(self, item):
        self.bucket[item.l] += 1
        self.bucket[item.r] += 1
        return self


    def outgoing(self, item):
        """ Lazily Expand the Hypergraph """
        i, j, h = item.i, item.j, item.h
        # items to the left
        # w = self.score(item)
        item = self.arc(item)
        all_arcs = []
        for k in range(0, i + 1):
            for g in range(k, i):
                if (k, i, g) in self.chart:
                    item_l = self.chart[(k, i, g)]
                    # lw = self.score(item_l)
                    item_l = self.arc(item_l)
                    #p = item_l.w * item.w
                    # p = lw * w  # item_l.w * item.w
                    # attach left arc
                    # yield Item(k, j, g, p * self.W[h, g], item_l, item)
                    all_arcs.append(Item(k, j, g, item_l, item))
                    #all_arcs.append(
                    #    (item_l, item,
                    #     Item(k, j, g, p * self.W[h, g], item_l, item)
                    #     )
                    #)
                    # attach right arc
                    # yield Item(k, j, h, p * self.W[g, h], item_l, item)
                    all_arcs.append(Item(k, j, h, item_l, item))
                    #all_arcs.append(
                    #    (item_l, item,
                    #     Item(k, j, h, p * self.W[g, h], item_l, item)
                    #     )
                    #)

        # items to the right
        for k in range(j, self.n + 1):
            for g in range(j, k):
                if (j, k, g) in self.chart:
                    item_r = self.chart[(j, k, g)]
                    item_r = self.arc(item_r)
                    # rw = self.score(item_r)
                    # p = rw * w  # item.w * item_r.w
                    # attach left arc
                    # yield Item(i, k, h, p * self.W[g, h], item, item_r)
                    all_arcs.append(Item(i, k, h, item, item_r))
                    #all_arcs.append(
                    #    (item, item_r,
                    #     Item(i, k, h, p * self.W[g, h], item, item_r)
                    #     )
                    #)
                    # attach right arc
                    # yield Item(i, k, g, p * self.W[h, g], item, item_r)
                    all_arcs.append(Item(i, k, g, item, item_r))
                    #all_arcs.append((
                    #    item,item_r,
                    #    Item(i, k, g, p * self.W[h, g], item, item_r)
                    #     )
                    #)
        return all_arcs


class LazyArcEager(Hypergraph):
    def __init__(self, n, chart, W):
        self.n = n
        self.chart = chart
        self.W = W

    def outgoing(self, item):
        pass


class LazyHybrid(Hypergraph):
    def __init__(self, n, chart, W):
        self.n = n
        self.chart = chart
        self.W = W

    def outgoing(self, item):
        pass


class LazyMH4(Hypergraph):
    def __init__(self, n, chart, W):
        self.n = n
        self.chart = chart
        self.W = W

    def outgoing(self, item):
        pass
