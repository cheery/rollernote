from __future__ import annotations
from typing import Union, Optional, Any
from dataclasses import dataclass
import logic as core

@dataclass
class Program:
    declarations : list[Declaration]

class Declaration:
    pass

@dataclass
class DataDeclaration(Declaration):
    name : str
    cons : list[Expr]
    lineno : int

    def register(self, builder):
        sig = self.name, 0
        builder.datadecls[sig] = self.cons, self.lineno

@dataclass
class TypeDeclaration(Declaration):
    name : str
    args : list[str]
    lineno : int

    def register(self, builder):
        sig = self.name, len(self.args)
        builder.typedecls[sig] = False, self.args, self.lineno

@dataclass
class RuleDeclaration(Declaration):
    name : str
    args : list[Expr]
    goal : Goal
    lineno : int

    def register(self, builder):
        sig = self.name, len(self.args)
        try:
            builder.rules[sig].append(self)
        except KeyError:
            builder.rules[sig] = [self]

    def variables(self):
        for arg in self.args:
            yield from arg.variables()
        yield from self.goal.variables()

@dataclass
class ConstraintDeclaration(Declaration):
    name : str
    args : list[str]
    lineno : int

    def register(self, builder):
        sig = self.name, len(self.args)
        builder.typedecls[sig] = True, self.args, self.lineno

@dataclass
class CHRDeclaration(Declaration):
    heads : list[(bool, str, list[Expr])]
    guards : list[(str, Expr, Expr)]
    goal : Goal
    lineno : int

    def register(self, builder):
        builder.chrd.append(self)

class Goal:
    pass

@dataclass
class Unify(Goal):
    a : Expr
    b : Expr

    def variables(self):
        yield from self.a.variables()
        yield from self.b.variables()

@dataclass
class Invoke(Goal):
    name : str
    args : list[Expr]

    def variables(self):
        for arg in self.args:
            yield from arg.variables()

    def construct(self, env, fnf):
        if self.name == 'true' and len(self.args) == 0:
            return []
        if self.name == 'fail' and len(self.args) == 0:
            return [core.Fail()]
        return [core.Invoke(self.name, *[a.as_core(env, fnf) for a in self.args])]

@dataclass
class Conj(Goal):
    a : Goal
    b : Goal

    def variables(self):
        yield from self.a.variables()
        yield from self.b.variables()

    def construct(self, env, fnf):
        a = self.a.construct(env, fnf)
        b = self.b.construct(env, fnf)
        return a + b

@dataclass
class Disj(Goal):
    a : Goal
    b : Goal

    def variables(self):
        yield from self.a.variables()
        yield from self.b.variables()

    def construct(self, env, fnf):
        a = self.a.construct(env, fnf)
        b = self.b.construct(env, fnf)
        return [core.Choice(len(a)+1)] + a + [core.Goto(len(b))] + b

class Expr:
    pass

@dataclass
class Term(Expr):
    functor : str
    args : list[Expr]

    def variables(self):
        for arg in self.args:
            yield from arg.variables()

    def as_core(self, env, fnf):
        functor = fnf.get(self.functor, self.functor)
        return core.Xt(functor, *[a.as_core(env, fnf) for a in self.args])

@dataclass
class Variable(Expr):
    name : str

    def variables(self):
        yield self.name

    def as_core(self, env, fnf):
        return core.Ix(env.index(self.name))

@dataclass
class IntLiteral(Expr):
    value : int

    def variables(self):
        return iter(())

    def as_core(self, env, fnf):
        return core.Const(self.value)

@dataclass
class StringLiteral(Expr):
    value : int

    def variables(self):
        return iter(())

    def as_core(self, env, fnf):
        return core.Const(self.value)

@dataclass
class Query(Declaration):
    goal : Goal
    lineno : int

    def register(self, builder):
        if builder.query is None:
            builder.query = self
        else:
            builder.query = Conj(builder.query, self)
