from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Union
from math import gcd

class Node:
    pass

@dataclass #(frozen=True)
class Zipper:
    pred : Optional[Zipper]
    weight : int
    left : tuple[Node]
    right : tuple[Node]

    def __init__(self, pred, weight, left, right):
        self.pred = pred
        self.weight = weight
        self.left = left
        self.right = right
        assert isinstance(self.left, tuple)
        assert isinstance(self.right, tuple)

    @property
    def finger(self):
        if self.pred:
            pred = self.pred.finger
        else:
            pred = None
        count = len(self.left) + 1 + len(self.right)
        return Finger(pred, len(self.left), count)

    def fold(self, focus):
        if isinstance(focus, int):
            this = self.left + (leaf(self.weight, focus),) + self.right
        else:
            focus = normalize(focus)
            this = self.left + (branch(self.weight, focus),) + self.right
        if self.pred:
            return self.pred.fold(this)
        return this

    @property
    def total_weight(self):
        w = self.weight
        w += sum(n.weight for n in self.left)
        w += sum(n.weight for n in self.right)
        return w

def finger_of(zipper):
    if zipper:
        return zipper.finger

def fold_of(zipper, focus):
    if zipper:
        return zipper.fold(focus)
    return tuple(focus)

@dataclass(frozen=True)
class Finger:
    pred : Optional[Finger]
    index : int
    count : int

    @property
    def depth(self):
        if self.pred:
            return self.pred.depth + 1
        return 0

    def common(self, other):
        ixs = self.unroll()
        iys = other.unroll()
        count = 0
        while len(ixs) > 1 and len(iys) > 1 and ixs[-1] == iys[-1]:
            ixs.pop()
            iys.pop()
            count += 1
        return count

    def __le__(self, other):
        ixs = self.unroll()
        iys = other.unroll()
        while len(ixs) > 1 and len(iys) > 1 and ixs[-1] == iys[-1]:
            ixs.pop()
            iys.pop()
        return ixs[-1] <= iys[-1]

    def order(self, other):
        if self <= other:
            return self, other
        else:
            return other, self

    def zipper(self, seq):
        pred = None
        for i in reversed(self.unroll()):
            pred = Zipper(pred, seq[i].weight, seq[:i], seq[i+1:])
            seq = seq[i]
        if isinstance(seq, Branch):
            item = seq.children
        else:
            item = seq.uid
        return pred, item

    def select(self, seq):
        if self.pred:
            seq = self.pred.select(seq)
            item = seq[self.index]
        else:
            item = seq[self.index]
        return item
        #if isinstance(item, Branch):
        #    return item.children
        #else:
        #    return item.uid

    def unroll(self):
        result = [self.index]
        while self.pred:
            result.append(self.pred.index)
            self = self.pred
        return result

    @property
    def is_leftmost(self):
        return self.index == 0

    @property
    def is_rightmost(self):
        return self.index + 1 == self.count

    def last_left_sibling(self):
        if not self.is_leftmost:
            return Finger(self.pred, self.index - 1, self.count)
        if self.pred:
            return self.pred.last_left_sibling()

    def last_right_sibling(self):
        if not self.is_rightmost:
            return Finger(self.pred, self.index + 1, self.count)
        if self.pred:
            return self.pred.last_right_sibling()

    def prev_uid(self, trees):
        if finger := self.last_left_sibling():
            return finger.select(trees).rightmost_finger(finger)

    def next_uid(self, trees):
        if finger := self.last_right_sibling():
            return finger.select(trees).leftmost_finger(finger)

    def __repr__(self):
        if self.pred:
            prefix = repr(self.pred) + ":"
        else:
            prefix = ""
        return f"{prefix}{self.index}_{self.count}"

def branch(weight, children):
    children = tuple(children)
    assert len(children) >= 2
    assert weight > 0
    return Branch(weight, children)

def leaf(weight, uid):
    assert isinstance(uid, int)
    assert weight > 0
    return Leaf(weight, uid)

@dataclass(frozen=True)
class Branch(Node):
    weight : Union[int, float]
    children : tuple[Node]

    @property
    def depth(self):
        return 1 + max(child.depth for child in self.children)

    def __len__(self):
        return len(self.children)

    def __getitem__(self, index):
        return self.children[index]

    def leftmost_finger(self, pred=None):
        return self[0].leftmost_finger(Finger(pred, 0, len(self)))

    def rightmost_finger(self, pred=None):
        return self[len(self) - 1].rightmost_finger(Finger(pred, len(self) - 1, len(self)))

    def strip(self):
        return self.children

    def op(self, f):
        return Branch(f(self.weight), self.children)

    def traverse(self, result):
        for child in self.children:
            child.traverse(result)
        return result

    def clone(self, uids):
        return Branch(self.weight, tuple(child.clone(uids) for child in self.children))

@dataclass(frozen=True)
class Leaf(Node):
    weight : Union[int, float]
    uid : int

    @property
    def depth(self):
        return 0

    def leftmost_finger(self, pred=None):
        return pred

    def rightmost_finger(self, pred=None):
        return pred

    def strip(self):
        return self.uid

    def op(self, f):
        return Leaf(f(self.weight), self.uid)

    def traverse(self, result):
        result.append(self.uid)
        return result

    def clone(self, uids):
        return Leaf(self.weight, next(uids))

def locate(trees, uid, finger=None):
    for i, tree in enumerate(trees):
        subfinger = Finger(finger, i, len(trees))
        if isinstance(tree, Leaf) and tree.uid == uid:
            return subfinger
        if isinstance(tree, Branch) and (result := locate(tree.children, uid, subfinger)):
            return result

@dataclass
class Uids:
    index : int = 0

    def __next__(self):
        self.index += 1
        return self.index

def normalize(nodes):
    divider = gcd(*(node.weight for node in nodes))
    if divider > 1:
        return [node.op(lambda w: w // divider) for node in nodes]
    else:
        return nodes

def normalize_tof(nodes, amount):
    divider = gcd(*(node.weight for node in nodes))
    total = sum(node.weight for node in nodes)
    m = amount / (total / divider)
    return tuple(node.op(lambda w: w * m / divider) for node in nodes)

def normalize_to(nodes, amount):
    divider = gcd(*(node.weight for node in nodes))
    total = sum(node.weight for node in nodes)
    if amount % (total // divider) == 0:
        m = amount // (total // divider)
        if divider > 1 or m > 1:
            return tuple(node.op(lambda w: w * m // divider) for node in nodes)
        else:
            return nodes
