from __future__ import annotations
from collections import defaultdict
from typing import Union, Optional, Any
from dataclasses import dataclass
import logic_ast as ast
import logic as core

@dataclass
class Builder:
    datadecls : dict[(str, int), (list[str], int)]
    termdecls : dict[(str, int), ((str, int), list[core.Expr])]
    typedecls : dict[(str, int), (bool, int, list[core.Expr], int)]
    rules : dict[(str, int), ast.RuleDeclaration]
    chrd : list[ast.CHRDeclaration]
    query : Optional[ast.Goal]

class Graph:
    def __init__(self, graph : defaultdict[list]):
        self.graph = graph

    # DFS helper function
    def _dfs(self, v, visited, component=None):
        visited[v] = True
        if component is not None:
            component.append(v)
        for i in self.graph[v]:
            if not visited[i]:
                self._dfs(i, visited, component)

    # Fill vertices in stack according to their finishing times
    def _fill_order(self, v, visited, stack):
        visited[v] = True
        for i in self.graph[v]:
            if not visited[i]:
                self._fill_order(i, visited, stack)
        stack.append(v)

    # Get the transpose of the graph
    def _get_transpose(self):
        g_transpose = defaultdict(list)
        for u in self.graph:
            for v in self.graph[u]:
                g_transpose[v].append(u)
        return Graph(g_transpose)

    # Function to find all strongly connected components
    def sccs(self):
        # Step 1: Perform a DFS to fill stack with vertices based on finish times
        stack = []
        visited = defaultdict(bool)
        for i in list(self.graph):
            if not visited[i]:
                self._fill_order(i, visited, stack)

        # Step 2: Create a reversed graph (transpose)
        g_transpose = self._get_transpose()

        # Step 3: Process all vertices in order defined by the stack
        visited = defaultdict(bool)
        sccs = []  # Store strongly connected components here
        while stack:
            v = stack.pop()
            if not visited[v]:
                component = []
                g_transpose._dfs(v, visited, component)
                sccs.append(component)
        return sccs

def generalize(t, env):
    if isinstance(t, core.Variable):
        return core.Ix(env.index(t))
    elif isinstance(t, core.Term):
        xargs = [generalize(a, env) for a in t.args]
        return core.Xt(t.functor, *xargs)
    else:
        return core.Const(t)
