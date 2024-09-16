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
    args : list[str]
    cons : list[(str, list[Expr])]
    lineno : int

    def register(self, builder):
        sig = self.name, len(self.args)
        tenv = self.args
        cons = []
        for name, targs in self.cons:
            xargs = [targ.as_core(tenv, {}) for targ in targs]
            cons.append((name, xargs))
            builder.termdecls[(name, len(targs))] = sig, xargs
        builder.datadecls[sig] = cons, self.lineno

@dataclass
class TypeDeclaration(Declaration):
    name : str
    args : list[Expr]
    lineno : int

    def register(self, builder):
        sig = self.name, len(self.args)
        tenv = []
        for a in self.args:
            tenv.extend(a.variables())
        tenv = list(set(tenv))
        xargs = [a.as_core(tenv, {}) for a in self.args]
        builder.typedecls[sig] = False, len(tenv), xargs, self.lineno

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
        tenv = []
        for a in self.args:
            tenv.extend(a.variables())
        tenv = list(set(tenv))
        xargs = [a.as_core(tenv, {}) for a in self.args]
        builder.typedecls[sig] = True, len(tenv), xargs, self.lineno

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

    def construct(self, env, fnf, typedecls):
        sig = self.name, len(self.args)
        if self.name == 'true' and len(self.args) == 0:
            return []
        if self.name == 'fail' and len(self.args) == 0:
            return [core.Fail()]
        if typedecls[sig][0]:
            fn = core.Constraint
        else:
            fn = core.Invoke
        return [fn(self.name, *[a.as_core(env, fnf) for a in self.args])]

    def references(self):
        if self.name == 'true' and len(self.args) == 0:
            pass
        elif self.name == 'fail' and len(self.args) == 0:
            pass
        else:
            yield self.name, len(self.args)

    def infer(self, tenv, termdecls, typedecls, refs, mutor):
        if self.name == 'true' and len(self.args) == 0:
            pass
        elif self.name == 'fail' and len(self.args) == 0:
            pass
        else:
            targs = [arg.infer(tenv, termdecls, mutor) for arg in self.args]
            sig = self.name, len(targs)
            if sig in refs:
                uargs = refs[sig]
            else:
                assert False, "TODO"
                aa, _ = typedecls[sig]
                uargs = [core.Term(a, []) for a in aa]
            for a, b in zip(uargs, targs):
                a = core.deepwalk(a, mutor.subs)
                b = core.deepwalk(b, mutor.subs)
                assert core.unify(a, b, mutor)

@dataclass
class Conj(Goal):
    a : Goal
    b : Goal

    def variables(self):
        yield from self.a.variables()
        yield from self.b.variables()

    def construct(self, env, fnf, typedecls):
        a = self.a.construct(env, fnf, typedecls)
        b = self.b.construct(env, fnf, typedecls)
        return a + b

    def references(self):
        yield from self.a.references()
        yield from self.b.references()

    def infer(self, tenv, termdecls, typedecls, mutor):
        self.a.infer(tenv, termdecls, typedecls, mutor)
        self.b.infer(tenv, termdecls, typedecls, mutor)

@dataclass
class Disj(Goal):
    a : Goal
    b : Goal

    def variables(self):
        yield from self.a.variables()
        yield from self.b.variables()

    def construct(self, env, fnf, typedecls):
        a = self.a.construct(env, fnf, typedecls)
        b = self.b.construct(env, fnf, typedecls)
        return [core.Choice(len(a)+1)] + a + [core.Goto(len(b))] + b

    def references(self):
        yield from self.a.references()
        yield from self.b.references()

    def infer(self, tenv, termdecls, typedecls, mutor):
        self.a.infer(tenv, termdecls, typedecls, mutor)
        self.b.infer(tenv, termdecls, typedecls, mutor)

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

    def infer(self, tenv, termdecls, mutor):
        sig = self.functor, len(self.args)
        (ty,n), xargs = termdecls[sig]
        tyenv = [core.Variable() for _ in range(n)]
        targs = [xarg.eva(tyenv, mutor.subs) for xarg in xargs]
        for ta, a in zip(targs, self.args):
            tb = a.infer(tenv, termdecls, mutor)
            ta = core.deepwalk(ta, mutor.subs)
            tb = core.deepwalk(tb, mutor.subs)
            assert core.unify(ta, tb, mutor)
        return core.Term(ty, tyenv)

@dataclass
class Variable(Expr):
    name : str

    def variables(self):
        yield self.name

    def as_core(self, env, fnf):
        return core.Ix(env.index(self.name))

    def infer(self, tenv, termdecls, mutor):
        return tenv[self.name]

@dataclass
class IntLiteral(Expr):
    value : int
    ty : Any

    def variables(self):
        return iter(())

    def as_core(self, env, fnf):
        return core.Const(self.value)

    def infer(self, tenv, termdecls, mutor):
        return self.ty

@dataclass
class StringLiteral(Expr):
    value : int
    ty : Any

    def variables(self):
        return iter(())

    def as_core(self, env, fnf):
        return core.Const(self.value)

    def infer(self, tenv, termdecls, mutor):
        return self.ty

@dataclass
class Query(Declaration):
    goal : Goal
    lineno : int

    def register(self, builder):
        if builder.query is None:
            builder.query = self
        else:
            builder.query.goal = Conj(builder.query.goal, self.goal)
