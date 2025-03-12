from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Union

@dataclass(frozen=True)
class Empty:
    height = 0
    balance = 0
    def __iter__(self):
        return iter(())

    def insert(self, key, value=None):
        return Node(key, value)

    def delete(self, key):
        raise KeyError

    def query(self, key):
        raise KeyError

empty = Empty()

@dataclass
class Node:
    key    : Any
    value  : Any
    left   : Union[Empty, Node] = empty
    right  : Union[Empty, Node] = empty
    height : int = field(init = False)

    def __post_init__(self):
        self.height = 1 + max(self.left.height, self.right.height)

    @property
    def balance(self):
        return self.left.height - self.right.height

    def __iter__(self):
        yield from self.left
        yield self.key, self.value
        yield from self.right

    def insert(node, key, value=None):
        if key < node.key:
            node = Node(node.key, node.value, node.left.insert(key, value), node.right)
        elif key > node.key:
            node = Node(node.key, node.value, node.left, node.right.insert(key, value))
        else:
            return Node(node.key, value, node.left, node.right)
        return rebalance(node)

    def delete(self, key):
        if key < self.key:
            node = Node(self.key, self.value, self.left.delete(key), self.right)
        elif key > self.key:
            node = Node(self.key, self.value, self.left, self.right.delete(key))
        else:
            if self.left is empty:
                return self.right
            elif self.right is empty:
                return self.left
            else:
                successor = self.right
                while successor.left is not empty:
                    successor = successor.left
                node = Node(successor.key, successor.value,
                            self.left, self.right.delete(successor.key))
        return rebalance(node)

    def query(self, key):
        if key < self.key:
            return self.left.query(key)
        elif key > self.key:
            return self.right.query(key)
        else:
            return self.value

def rebalance(node):
    balance = node.balance
    if balance > 1:
        if node.left.balance >= 0:
            return right_rotate(node)
        else:
            temp = Node(node.key, node.value, left_rotate(node.left), node.right)
            return right_rotate(temp)
    elif balance < -1:
        if node.right.balance <= 0:
            return left_rotate(node)
        else:
            temp = Node(node.key, node.value, node.left, right_rotate(node.right))
            return left_rotate(temp)
    return node

def right_rotate(z):
    x = z.left
    y = x.right
    return Node(x.key, x.value, x.left, Node(z.key, z.value, y, z.right))

def left_rotate(x):
    z = x.right
    y = z.left
    return Node(z.key, z.value, Node(x.key, x.value, x.left, y), z.right)

Avl = Union[Empty, Node]

if __name__=='__main__':
    root = empty
    root = root.insert(10)
    root = root.insert(20)
    root = root.insert(30)
    root = root.insert(40)
    root = root.insert(50)
    root = root.insert(25)
    root = root.delete(40)
    
    for i in root:
        print(i)
