from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from contextvars import ContextVar
from immutables import Map, MapMutation
from typing import Union, Optional, Any, Callable

from .avl import empty, Avl
from .structures import Variable, Structure, Show, term

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
    alt    : deque[Answer]

    def __init__(self, module):
        self.module = module
        self.alt    = deque()

    def run(self):
        while self.alt:
            answer = self.alt.pop()
            try:
                while answer.cont:
                    cont = answer.cont
                    command = cont.code[cont.pc]
                    cont.pc += 1
                    command(answer)
                yield answer
            except Halt:
                pass

    def answer(self, *args, **kwargs):
        self.alt.append(Answer(self, *args, **kwargs))
 
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
class Answer:
    stream : Stream
    cont : Optional[Cont] = None
    subs : Map[Variable, Any] = Map()
    sus  : Map[Variable, (Any, Any)] = Map()
    ans  : Avl = empty

    def copy(self, **kwargs):
        answer = Answer(self.stream, self.cont, self.subs, self.sus, self.ans)
        for k,v in kwargs.items():
            setattr(answer, k, v)
        return answer

    def invoke(self, attr, val):
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

    def bind(self, a, x):
        if self.occurs(a, x):
            return False
        self.subs = self.subs.set(a, x)
        try:
            susps = self.sus[a]
        except KeyError:
            pass
        else:
            self.sus = self.sus.delete(a)
            for susp in susps:
                if self.ground(susp):
                    self.invoke(*susp)
                else:
                    self.suspension(susp)
        return True

    def suspension(self, record):
        for v in self.occurrences(record):
            self.sus = self.sus.set(v, self.sus.get(v, []) + [record])

    def suspended(self):
        for susps in self.sus.values():
            yield from susps

    def deref(self, a):
        while isinstance(a, Variable) and a in self.subs:
            a = self.subs[a]
        return a

    def occurs(self, a, x):
        x = self.deref(x)
        if a is x:
            return True
        elif isinstance(x, Structure):
            return self.occurs(a, x.args)
        elif isinstance(x, tuple):
            return any(self.occurs(a, y) for y in x)
        else:
            return False

    def ground(self, x):
        x = self.deref(x)
        if isinstance(x, Variable):
            return False
        elif isinstance(x, Structure):
            return self.ground(x.args)
        elif isinstance(x, tuple):
            return all(self.ground(y) for y in x)
        return True

    def occurrences(self, x):
        x = self.deref(x)
        if isinstance(x, Variable):
            yield x
        elif isinstance(x, Structure):
            yield from self.occurrences(x.args)
        elif isinstance(x, tuple):
            for y in x:
                yield from self.occurrences(y)
    
    def unify(self, x, y):
        x = self.deref(x)
        y = self.deref(y)
        if x is y:
            return True
        elif isinstance(x, Variable):
            return self.bind(x,y)
        elif isinstance(y, Variable):
            return self.bind(y,x)
        elif isinstance(x, Structure) and isinstance(y, Structure):
            if x.functor == y.functor:
                return self.unify(x.args, y.args)
            else:
                return False
        elif isinstance(x, tuple) and isinstance(y, tuple):
            if len(x) == len(y):
                return all(self.unify(x,y) for x,y in zip(x, y))
            else:
                return False
        else:
            return False

    def walk(self, x):
        x = self.deref(x)
        if isinstance(x, Structure):
            return Structure(x.functor, self.walk(x.args))
        elif isinstance(x, tuple):
            return tuple(self.walk(a) for a in x)
        else:
            return x

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
class Const(Expr):
    value : Any
    def evaluate(self, env : Env):
        return self.value

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
        answer.invoke(term.New(self.name, args), val)
        if self.recursive:
            answer.stream.alt.appendleft(answer)
            raise Halt

@dataclass
class Function:
    arity : int
    code : Code
    ground : bool = False
    def enter(self, answer, attr, val):
        assert self.arity == len(attr.args)
        if self.ground and not answer.ground(attr) and not answer.ground(val):
            answer.suspension((attr, val))
        else:
            answer.cont = Cont(list(attr.args) + [val], self.code, cont=answer.cont)

@dataclass
class Assertion:
    arity : int
    def enter(self, answer, attr, val):
        assert self.arity == len(attr.args)
        if answer.ground(attr) and answer.ground(val):
            answer.ans = answer.ans.insert(attr, val)
        else:
            answer.suspension((attr, val))

def query_generator(dataset, pattern):
    for record in dataset:
        yield record
 
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
        if self.ground and not answer.ground(attr) and not answer.ground(val):
            answer.suspension((attr, val))
        else:
            gen = query_generator(self.data, answer.walk(attr))
            try:
                record = next(gen)
            except StopIteration:
                raise Halt
            alt = Cont([], [ResumeQuery(gen, (attr,val)), Proceed()], cont=answer.cont.copy())
            answer.stream.alt.append(answer.copy(cont=alt))
            if not answer.unify(record, (attr,val)):
                raise Halt

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
    def __call__(self, ab : Stream, frame : Frame):
        raise Halt
 
if __name__=='__main__':
    module = {
        "bar": Assertion(2),
        "foo": Function(2, [
            Invoke("bar", [Ix(0), Ix(1)], Ix(2)),
            Proceed(),
        ]),
    }

    X, Y = Variable(), Variable()
    code = [
        Choice(2),
        Unify(Xt("term", [Ix(0)]), Ix(1)),
        Proceed(),
        Choice(3),
        Invoke("bar", [Xt("foo", []), Xt("bar", [])], Xt("unit", [])),
        Unify(Xt("turm", [Ix(1)]), Ix(0)),
        Proceed(),
        Invoke("bar", [Xt("foo", []), Ix(0)], Xt("unit", [])),
        Invoke("foo", [Ix(0), Ix(1)], Xt("unit", [])),
        Proceed(),
    ]

    stream = Stream(module)
    stream.answer(Cont([X,Y], code))
    for answer in stream.run():
        show = Show(names = {X: "X", Y: "Y"})
        print(f"{show(answer.walk(X), 5)}, {show(answer.walk(Y), 5)}")
        for attr, val in answer.ans:
            print(f"  {show(answer.walk(attr),5)} is {show(answer.walk(val),5)}")
        for attr, val in set(answer.suspended()):
            print(f"  [{show(answer.walk(attr),5)} is {show(answer.walk(val),5)}]")
