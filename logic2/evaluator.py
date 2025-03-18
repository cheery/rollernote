from __future__ import annotations
from collections import deque, namedtuple
from dataclasses import dataclass
from contextvars import ContextVar
from immutables import Map, MapMutation
from typing import Union, Optional, Any, Callable

from .avl import empty, Avl
from .structures import Variable, Structure, Kernel, Show, term
from .query import query_pattern

class Command:
    pass

class Expr:
    pass

Code      = list[Command]
Module    = dict[str, Any]
Env       = list[Any]

class Halt(Exception):
    pass

@dataclass
class Stream:
    module : Module
    rules  : list[(list[(Any,Any)], list[Any], Code)]
    index  : dict[str, list[(int, int)]]
    alt    : deque[Answer]

    def branch(self, answers):
        return Stream(self.module, self.rules, self.index, deque(answers))

    @classmethod
    def new(cls, module, rules):
        return cls(module, rules, make_index(rules), deque())

    def run(self):
        while self.alt:
            answer = self.alt.pop()
            try:
                rollforward(answer)
                while answer.cont:
                    cont = answer.cont
                    command = cont.code[cont.pc]
                    cont.pc += 1
                    command(answer)
                if answer.neg is empty:
                    yield answer
            except Halt:
                pass

    def answer(self, *args, **kwargs):
        answer = Answer(self, *args, **kwargs)
        fire_empty(answer, self.rules)
        self.alt.append(answer)
 
def make_index(rules):
    index = dict()
    for i, (precedents, _, _) in enumerate(rules):
        for j, (attr, _) in enumerate(precedents):
            index.setdefault(attr.functor, []).append((i,j))
    return index

def fire_empty(answer, rules):
    for precedents, env, code in rules:
        if len(precedents) == 0:
            assert len(env) == 0
            answer.cont = Cont(env, code, cont=answer.cont)

@dataclass
class Cont:
    env  : Env
    code : Code
    pc   : int = 0
    cont : Optional[Cont] = None

    def copy(self, **kwargs):
        cont = Cont(self.env, self.code, self.pc, self.cont)
        for k,v in kwargs.items():
            setattr(cont, k, v)
        return cont

@dataclass
class Answer(Kernel):
    stream : Stream
    cont : Optional[Cont] = None
    subs : Map[Variable, Any] = Map()
    sus  : Map[int, Any] = Map()
    susi : Map[Variable, list[int]] = Map()
    susn : int = 0
    ans  : Avl = empty
    neg  : Avl = empty
    pen  : Optional[(Any,Any)] = None

    def copy(self, **kwargs):
        answer = Answer(self.stream,
            self.cont, self.subs,
            self.sus, self.susi, self.susn,
            self.ans, self.neg, self.pen)
        for k,v in kwargs.items():
            setattr(answer, k, v)
        return answer

    def query(self, attr, val):
        entry = self.stream.module[attr.functor]
        entry.query(self, attr, val)

    def invoke(self, attr, val, _):
        #if attr.functor.startswith('!'):
        #    pos = term.New(attr.functor[1:], attr.args)
        #    if self.ground(pos) and self.ground(val):
        #        pos = self.walk(pos)
        #        val = self.walk(val)
        #        stream = Stream(self.stream.module)
        #        stream.answer(Cont([], [Invoke(pos.functor, pos.args, val), Proceed()]))
        #        for _ in stream.run():
        #            assert False
        #    else:
        #        self.suspension((attr, val))
        #else:
        entry = self.stream.module[attr.functor]
        entry.enter(self, attr, val)

    def invoke_choice(self, attr, vals, _, open):
        entry = self.stream.module[attr.functor]
        entry.enter_choice(self, attr, vals, open)

    def bind(self, a, x):
        if not super().bind(a,x):
            return False
        try:
            indices = self.susi[a]
        except KeyError:
            pass
        else:
            self.susi = self.susi.delete(a)
            susps = []
            for n in indices:
                susp = self.sus[n]
                if self.ground_susp(susp):
                    self.sus = self.sus.delete(n)
                    susps.append(Unsuspend(susp))
            if len(susps) > 0:
                susps.append(Proceed())
                self.cont = Cont([], susps, cont=self.cont)
        return True

    def suspension(self, record):
        n, self.susn = self.susn, self.susn + 1
        self.sus = self.sus.set(n, record)
        if record[2] & 1 > 0:
            for v in self.occurrences(record[0]):
                self.susi = self.susi.set(v, self.susi.get(v, []) + [n])
        if record[2] & 2 > 0:
            for v in self.occurrences(record[1]):
                self.susi = self.susi.set(v, self.susi.get(v, []) + [n])

    def suspended(self):
        for record in self.sus.values():
            yield record

    def ground_susp(self, record):
        ground = True
        if record[2] & 1 > 0:
            ground &= self.ground(record[0])
        if record[2] & 2 > 0:
            ground &= self.ground(record[1])
        return ground

@dataclass
class Ix(Expr):
    index : int
    def evaluate(self, env : Env):
        return env[self.index]

@dataclass
class Xt(Expr):
    functor : str
    args : list[Expr]
    def evaluate(self, env : Env):
        args = tuple(a.evaluate(env) for a in self.args)
        return term.New(self.functor, args)

@dataclass
class Tu(Expr):
    args : list[Expr]
    def evaluate(self, env : Env):
        return tuple(a.evaluate(env) for a in self.args)

@dataclass
class Const(Expr):
    value : Any
    def evaluate(self, env : Env):
        return self.value

@dataclass
class Unsuspend(Command):
    susp : Any
    def __call__(self, answer : Answer):
        susp = self.susp
        if len(susp) == 3:
            answer.invoke(*susp)
        else:
            answer.invoke_choice(*susp)

@dataclass
class Query(Command):
    name : str
    args : list[Expr]
    val  : Expr
    def __call__(self, answer : Answer):
        env = answer.cont.env
        args = tuple(a.evaluate(env) for a in self.args)
        val  = self.val.evaluate(env)
        answer.query(term.New(self.name, args), val)

@dataclass
class Invoke(Command):
    name : str
    args : list[Expr]
    val  : Expr
    tail_call : bool = False
    recursive : bool = False

    def __call__(self, answer : Answer):
        env = answer.cont.env
        args = tuple(a.evaluate(env) for a in self.args)
        val  = self.val.evaluate(env)
        if self.tail_call:
            cont = answer.cont.cont
            if cont is not None:
                cont = cont.copy()
            answer.cont = cont
        answer.invoke(term.New(self.name, args), val, 0)
        if self.recursive:
            answer.stream.alt.appendleft(answer)
            raise Halt

@dataclass
class InvokeChoice(Command):
    name : str
    args : list[Expr]
    vals : list[Expr]
    open : bool = False
    def __call__(self, answer : Answer):
        env = answer.cont.env
        args = tuple(a.evaluate(env) for a in self.args)
        vals = tuple(v.evaluate(env) for v in self.vals)
        answer.invoke_choice(term.New(self.name, args), vals, 0, self.open)

@dataclass
class Function:
    arity : int
    code : Code
    ground : bool = False
    def enter(self, answer, attr, val):
        assert self.arity == len(attr.args)
        if self.ground and not answer.ground(attr):
            answer.suspension((attr, val, 1))
        else:
            answer.cont = Cont(list(attr.args) + [val], self.code, cont=answer.cont)

    def enter_choice(self, answer, attr, vals, open):
        if len(vals) == 1 and open == False:
            self.enter(answer, attr, vals[0])
        else:
            assert False

just = namedtuple("just", ["value"])
noneOf = namedtuple("noneOf", ["values"])

def merge(a, b):
    match (a,b):
        case (just(a), just(b)) if a == b:
            return just(a)
        case (noneOf(a), just(b)) if b not in a:
            return just(b)
        case (just(a), noneOf(b)) if a not in b:
            return just(a)
        case (noneOf(a), noneOf(b)):
            return noneOf(a | b)
        case _:
            return None

def assertion(answer, attr, opt):
    try:
        val = answer.ans.query(attr)
        if merge(just(val), opt):
            return
        else:
            raise Halt
    except KeyError:
        pass
    try:
        vals = answer.neg.query(attr)
        if not merge(noneOf(vals), opt):
            raise Halt
    except KeyError:
        pass
    assert answer.pen is None
    answer.pen = (attr, opt)

@dataclass
class Assertion:
    arity : int
    def query(self, answer, attr, val):
        assert self.arity == len(attr.args)
        gen = query_pattern(answer.ans, answer.walk(attr))
        try:
            record = next(gen)
        except StopIteration:
            raise Halt
        alt = Cont([], [ResumeQuery(gen, (attr,val)), Proceed()], cont=answer.cont.copy())
        answer.stream.alt.append(answer.copy(cont=alt))
        if not answer.unify(record, (attr,val)):
            raise Halt

    def enter(self, answer, attr, val):
        assert self.arity == len(attr.args)
        attr = answer.walk(attr)
        val  = answer.walk(val)
        if answer.ground((attr, val)):
            assertion(answer, attr, just(val))
            rollforward(answer)
        else:
            answer.suspension((attr, val, 3))

    def enter_choice(self, answer, attr, vals, open):
        assert self.arity == len(attr.args)
        attr = answer.walk(attr)
        vals = answer.walk(vals)
        if answer.ground((attr, vals)):
            for val in vals:
                subanswer = answer.copy(cont=answer.cont.copy())
                try:
                    assertion(subanswer, attr, just(val))
                    answer.stream.alt.append(subanswer)
                except Halt:
                    pass
            if open:
                assertion(answer, attr, noneOf(set(vals)))
                rollforward(answer)
            else:
                raise Halt
        else:
            answer.suspension((attr, vals, 3, open))

def rollforward(answer):
    if answer.pen is not None:
        attr, opt = answer.pen
        answer.pen = None
        match opt:
            case just(val):
                answer.ans = answer.ans.insert(attr, val)
                try:
                    answer.neg = answer.neg.delete(attr)
                except KeyError:
                    pass
                select(answer, attr, val)
            case noneOf(vals):
                answer.neg = answer.neg.insert(attr, vals)

def select(answer, attr, val):
    rules = answer.stream.rules
    for index, column in answer.stream.index.get(attr.functor, []):
        precedents, env, code = rules[index]
        subanswer = Kernel()
        if subanswer.unify((attr, val), precedents[column]):
            stream = [subanswer.subs]
            for i, (attr2, val2) in enumerate(precedents):
                if i == column:
                    continue
                new_stream = []
                for subs in stream:
                    subanswer = Kernel(subs)
                    for record in query_pattern(answer.ans, subanswer.walk(attr2)):
                        if subanswer.unify((attr2, val2), record):
                            new_stream.append(subanswer.subs)
                stream = new_stream
            for subs in stream:
                subanswer = Kernel(subs=subs)
                subenv = [subanswer.walk(x) for x in env]
                assert all(subanswer.ground(x) for x in subenv)
                answer.cont = Cont(subenv, code, cont=answer.cont)

@dataclass
class ResumeQuery(Command):
    gen: Any
    record : Any
    def __call__(self, answer : Answer):
        try:
            record = next(self.gen)
        except StopIteration:
            raise Halt
        pc = answer.cont.pc
        answer.stream.alt.append(answer.copy(cont=answer.cont.copy(pc = pc - 1)))
        if not answer.unify(record, self.record):
            raise Halt
 
@dataclass
class Dataset:
    arity : int
    data  : Avl
    ground : bool = False
    def enter(self, answer, attr, val):
        assert self.arity == len(attr.args)
        if self.ground and not answer.ground(attr):
            answer.suspension((attr, val, 1))
        else:
            gen = query_pattern(self.data, answer.walk(attr))
            try:
                record = next(gen)
            except StopIteration:
                raise Halt
            alt = Cont([], [ResumeQuery(gen, (attr,val)), Proceed()], cont=answer.cont.copy())
            answer.stream.alt.append(answer.copy(cont=alt))
            if not answer.unify(record, (attr,val)):
                raise Halt

    def enter_choice(self, answer, attr, vals, open):
        if len(vals) == 1 and open == False:
            self.enter(answer, attr, vals[0])
        else:
            assert False

@dataclass
class Goto(Command):
    offset : int
    def __call__(self, answer : Answer):
        answer.cont.pc += self.offset
 
@dataclass
class Choice(Command):
    offset : int
    def __call__(self, answer : Answer):
        pc = answer.cont.pc
        answer.stream.alt.append(
            answer.copy(
                cont=answer.cont.copy(pc = pc + self.offset)))

@dataclass
class Fresh(Command):
    count : int
    def __call__(self, answer : Answer):
        for _ in range(self.count):
            frame.cont.env = [Variable()] + frame.cont.env

@dataclass
class Unify(Command):
    x : Expr
    y : Expr
    def __call__(self, answer : Answer):
        x = self.x.evaluate(answer.cont.env)
        y = self.y.evaluate(answer.cont.env)
        if not answer.unify(x, y):
            raise Halt

@dataclass
class Proceed(Command):
    def __call__(self, answer : Answer):
        cont = answer.cont.cont
        if cont is not None:
            cont = cont.copy()
        answer.cont = cont

@dataclass
class Fail(Command):
    def __call__(self, answer : Answer):
        raise Halt

@dataclass
class Aggregation(Command):
    part : Expr
    group : Expr
    subcode : Code
    order_by : Optional[Expr]
    def __call__(self, answer : Answer):
        varset = set(self.occurrences(tuple(answer.cont.env)))
        group  = self.group.evaluate(answer.cont.env)
        part   = self.part.evaluate(answer.cont.env)
        if self.order_by is None:
            order_by = None
        else:
            order_by = self.order_by.evaluate(subenv)
        partition = tuple(varset - set(self.occurrences(group)))

        subanswer = answer.copy(cont=Cont(subenv, self.subcode))
        stream = answer.stream.branch([subanswer])
        partitions = dict()
        for subanswer in stream.run():
            #subanswer.sub = prune(subanswer.sub, varset)
            key = subanswer.walk(partition)
            key2 = subanswer.walk(part)
            p = partitions.setdefault(key, dict())
            p.setdefault(key2, []).append(subanswer)
        nsubs = set()
            #nsubs = set()
            #for _, ppsubs in partitions.items():
            #    if order is not None:
            #        ppsubs.sort(key = sort_key)
            #    ag = []
            #    rankvar = None
            #    for var, func, params in aggregations:
            #        if func == 'max':
            #            ag.append((var, max(evaluate(params[0], psub) for psub in ppsubs)))
            #        elif func == 'min':
            #            ag.append((var, min(evaluate(params[0], psub) for psub in ppsubs)))
            #        elif func == 'sum':
            #            ag.append((var, sum(evaluate(params[0], psub) for psub in ppsubs)))
            #        elif func == 'avg':
            #            ag.append((var, sum(evaluate(params[0], psub) for psub in ppsubs) / len(ppsubs)))
            #        elif func == 'count':
            #            ag.append((var, len(ppsubs)))
            #        elif func == 'rank':
            #            rankvar = var
            #        else:
            #            assert False, f"unknown aggregate function {func}"
            #    for i, psub in enumerate(ppsubs):
            #        if rankvar is not None:
            #            psub = unify(i, evaluate(rankvar, psub), psub)
            #        for var, value in ag:
            #            if psub is not None:
            #                psub = unify(evaluate(var, psub), value, psub)
            #        if psub is None:
            #            continue
            #        nsubs.add(prune(psub, occ))
            #if nsubs:
            #    cb[2](nsubs, pivot, work, store, new, era, cn)

def prune(subs, varset):
    a = Kernel(subs)
    return Map({k:a.walk(v) for k,v in subs.items() if k in varset})

if __name__=='__main__':
    module = {
        "edge": Assertion(2),
        "bar": Assertion(2),
        "foo": Function(2, [
            Invoke("bar", [Ix(0), Ix(1)], Ix(2)),
            Proceed(),
        ]),
    }
    X = Variable()
    Y = Variable()
    Z = Variable()
    rules = [
        ([], [], [Invoke("edge", [Const(1), Const(2)], Xt("unit", []), tail_call=True)]),
        ([], [], [Invoke("edge", [Const(2), Const(3)], Xt("unit", []), tail_call=True)]),
        ([(term.edge(X,Y), term.unit()), (term.edge(Y,Z), term.unit())],
         [X,Z],
         [Invoke("edge", [Ix(0), Ix(1)], Xt("unit", []), tail_call=True)])
    ]

    X, Y = Variable(), Variable()
    code = [
        Choice(2),
        Unify(Xt("term", [Ix(0)]), Ix(1)),
        Proceed(),
        Choice(3),
        Invoke("bar", [Xt("foo", []), Xt("bar", [])], Xt("unit", [])),
        Unify(Xt("turm", [Ix(1)]), Ix(0)),
        Proceed(),
        InvokeChoice("bar", [Xt("foo", []), Ix(0)],
                            [Xt("unit", []), Xt("baz", [])], open=True),
        InvokeChoice("bar", [Xt("foo", []), Ix(0)],
                            [Xt("unit", []), Xt("bar", [])], open=True),
        Invoke("foo", [Xt("baz", []), Ix(1)], Xt("unit", [])),
        Unify(Ix(0), Const(2)),
        Query("edge", [Const(1), Ix(1)], Xt("unit", [])),
        Proceed(),
    ]

    stream = Stream.new(module, rules)
    stream.answer(Cont([X,Y], code))
    for answer in stream.run():
        show = Show(names = {X: "X", Y: "Y"})
        print(f"{show(answer.walk(X), 5)}, {show(answer.walk(Y), 5)}")
        for attr, val in answer.ans:
            print(f"  {show(answer.walk(attr),5)} is {show(answer.walk(val),5)}")
        for record in set(answer.suspended()):
            if len(record) == 3:
                attr, val, _ = record
                print(f"  [{show(answer.walk(attr),5)} is {show(answer.walk(val),5)}]")
            elif record[3]:
                attr, vals, _, _ = record
                if len(vals) == 1:
                    s = show(answer.walk(vals[0]))
                else:
                    s = show(answer.walk(vals))
                print(f"  [{show(answer.walk(attr),5)} is? {s}]")
            else:
                attr, vals, _, _ = record
                if len(vals) == 1:
                    s = show(answer.walk(vals[0]))
                else:
                    s = show(answer.walk(vals))
                print(f"  [{show(answer.walk(attr),5)} is {s}]")

