from __future__ import annotations
from collections import namedtuple
from collections.abc import Callable
from typing import Union, Optional, Any
from dataclasses import dataclass
from immutables import Map, MapMutation
import itertools
import operator

# Function functor
@dataclass
class FnF:
    name : str
    fn   : Callable[..., Any]

@dataclass
class Mutor:
    subs : MapMutation[Variable, Any]
    vari : list[(Variable, Any)]

@dataclass(eq=True, frozen=True)
class CID:
    name : str
    args : tuple[Any]

    @property
    def signature(self):
        return self.name, len(self.args)

    def show(self, show_fn):
        args = ", ".join(map(show_fn, self.args))
        return f"{self.name}({args})"

@dataclass
class CHR:
    head : list[(str, int)]
    guards : list[Guard]
    goal : Code
    deletes : tuple[int]
    def __init__(self, head, guards, goal, deletes=()):
        self.head = head
        self.guards = guards
        self.goal = goal
        self.deletes = deletes

@dataclass
class CHRProgram:
    occ : dict[(str, int), list[(CHR, int)]]
    def __init__(self, chrs : list[CHR]):
        self.occ = {}
        for _chr in chrs:
            for i, cons in enumerate(_chr.head):
                try:
                    self.occ[cons].append((_chr, i))
                except KeyError:
                    self.occ[cons] = [(_chr, i)]

class Variable:
    def __repr__(self):
        return '_'

Term = namedtuple('Term', ['functor', 'args'])

class Command:
    pass

Subs = Union[Map[Variable, Any], MapMutation[Variable, Any]]
Code = list[Command]
Module = dict[(str, int), Code]
Env = list[Any]

@dataclass
class Cont:
    cont : Optional[Cont]
    env  : Env
    code : Code
    pc   : int

@dataclass
class Alt:
    prev  : Optional[Alt]
    frame : Optional[Frame]

@dataclass
class Frame:
    alt    : Optional[Alt]
    subs   : Subs
    chrs   : CHRStore
    cont   : Cont

@dataclass
class Stream:
    module : Module
    chrp   : CHRProgram
    frame  : Optional[Frame]

def init_frame(env, code, pc=0):
    chrs = CHRStore(Map(), Map(), Map())
    return Frame(None, Map(), chrs, Cont(None, env, code, pc))

def run(stream):
    while stream.frame:
        cont = stream.frame.cont
        command = cont.code[cont.pc]
        cont.pc += 1
        if (subs := command(stream)) is not None:
            yield subs
        
class Expr:
    pass

@dataclass
class Ix(Expr):
    index : int

    def eva(self, env : Env, subs : Subs):
        return deepwalk(env[self.index], subs)

class Xt(Expr):
    def __init__(self, functor, *args : list[Expr]):
        self.functor = functor
        self.args = args

    def eva(self, env : Env, subs : Subs):
        args = [a.eva(env, subs) for a in self.args]
        if isinstance(self.functor, FnF):
            if not any(isinstance(a, Variable) for a in args):
                return self.functor.fn(*args)
        return Term(self.functor, args)

    def __repr__(self):
        args = ", ".join(map(repr, self.args))
        return f"Xt({repr(self.functor)}, {args})"

@dataclass
class Const(Expr):
    value : Any

    def eva(self, env : Env, subs : Subs):
        return self.value

class Invoke(Command):
    def __init__(self, name : str, *args : list[Expr]):
        self.name = name
        self.args = args

    def __call__(self, ab : Stream):
        env = ab.frame.cont.env
        args = [a.eva(env, ab.frame.subs) for a in self.args]
        code = ab.module[(self.name, len(args))]
        ab.frame.cont = Cont(ab.frame.cont, args, code, pc=0)
        this = ab.frame.cont
        while this.cont:
            this = this.cont
            if this.code is code:
                ab.frame = delay(ab.frame)
                return

@dataclass
class Goto(Command):
    pc : int

    def __call__(self, ab : Stream):
        ab.frame.cont.pc += self.pc

@dataclass
class Choice(Command):
    pc : int

    def __call__(self, ab : Stream):
        pc = ab.frame.cont.pc
        chrs = CHRStore(ab.frame.chrs.live,
                        ab.frame.chrs.backlinks,
                        ab.frame.chrs.history)
        cont = Cont(ab.frame.cont.cont, ab.frame.cont.env, ab.frame.cont.code, pc + self.pc)
        ab.frame.alt = Alt(ab.frame.alt, None)
        ab.frame.alt.frame = Frame(ab.frame.alt, ab.frame.subs, chrs, cont)

@dataclass
class Fresh(Command):
    count : int

    def __call__(self, ab : Stream):
        for _ in range(self.count):
            ab.frame.cont.env = [Variable()] + ab.frame.cont.env

@dataclass
class Unify(Command):
    a : Expr
    b : Expr

    def __call__(self, ab : Stream):
        a = self.a.eva(ab.frame.cont.env, ab.frame.subs)
        b = self.b.eva(ab.frame.cont.env, ab.frame.subs)
        mutor = Mutor(ab.frame.subs.mutate(), [])
        if unify(a, b, mutor):
            ab.frame.subs = mutor.subs.finish()
            ids = set()
            for var, val in mutor.vari:
                try:
                    _ids = ab.frame.chrs.backlinks[var]
                    ab.frame.chrs.backlinks = ab.frame.chrs.backlinks.delete(var)
                except KeyError:
                    pass
                else:
                    for cid in _ids:
                        for var in occurrences(val, ab.frame.subs):
                            ab.frame.chrs.connect(var, cid)
                    ids.update(_ids)
            for cid in ids:
                ab.frame = ab.frame.chrs.occurrences(ab.chrp, ab.frame, cid)
        else:
            ab.frame = delay(fail(ab.frame))
        
class Success(Command):
    def __call__(self, ab : Stream):
        subs = ab.frame.subs
        chrs = ab.frame.chrs
        if ab.frame.cont.cont is None:
            ab.frame = delay(fail(ab.frame))
            return subs, chrs
        else:
            cont = ab.frame.cont.cont
            ab.frame.cont = Cont(cont.cont, cont.env, cont.code, cont.pc)

class Fail(Command):
    def __call__(self, ab : Stream):
        ab.frame = fail(ab.frame)

class Constraint(Command):
    def __init__(self, name, *args):
        self.name = name
        self.args = args
    
    def __call__(self, ab : Stream):
        args = [a.eva(ab.frame.cont.env, ab.frame.subs) for a in self.args]
        cid = ab.frame.chrs.add(self.name, args)
        for arg in cid.args:
            for var in occurrences(arg, ab.frame.subs):
                ab.frame.chrs.connect(var, cid)
        ab.frame = ab.frame.chrs.occurrences(ab.chrp, ab.frame, cid)

def delay(frame):
    if frame:
        while frame.alt and not frame.alt.frame:
            frame.alt = frame.alt.prev
        alt = frame.alt
        while alt:
            alt.frame, frame = frame, alt.frame
            while alt.prev and not alt.prev.frame:
                alt.prev = alt.prev.prev
            alt = alt.prev
    return frame

def fail(frame):
    alt = frame.alt
    while alt:
        if alt.frame:
            alt.frame, frame = None, alt.frame
            return frame
        alt = alt.prev

def unify(u, v, mutor : Mutor):
    if isinstance(u, Variable) and isinstance(v, Variable) and u is v:
        return True
    elif isinstance(u, Variable):
        if not occurs(u, v, mutor.subs):
            mutor.subs[u] = v
            mutor.vari.append((u, v))
            return True
    elif isinstance(v, Variable):
        if not occurs(v, u, mutor.subs):
            mutor.subs[v] = u
            mutor.vari.append((v, u))
            return True
    elif u.functor == v.functor and len(u.args) == len(v.args):
        for a,b in zip(u.args, v.args):
            if not unify(a, b, mutor):
                return False
        return True
    return False

def eq(u, v, subs : Subs):
    if isinstance(u, Term) and isinstance(v, Term):
        for a,b in zip(u.args, v.args):
            if not eq(a, b, subs):
                return False
        return True
    return u == v

def occurrences(v : Any, subs : Subs):
    v = walk(v, subs)
    if isinstance(v, Variable):
        yield v
    if isinstance(v, Term):
        for a in v.args:
            yield from occurrences(a, subs)

def occurs(u : Variable, v : Any, subs : Subs):
    v = walk(v, subs)
    if u is v:
        return True
    if isinstance(v, Term):
        return any(occurs(u, a, subs) for a in v.args)
    return False

def deepwalk(t, subs : Subs):
    while isinstance(t, Variable) and t in subs:
        t = subs[t]
    if isinstance(t, Term):
        args = [deepwalk(a, subs) for a in t.args]
        if isinstance(t.functor, FnF):
            if not any(isinstance(a, Variable) for a in args):
                return t.functor.fn(*args)
        return Term(t.functor, args)
    return t

def walk(t, subs : Subs):
    while isinstance(t, Variable) and t in subs:
        t = subs[t]
    # Attempt to evaluate the term if a function functor
    if isinstance(t, Term) and isinstance(t.functor, FnF):
        args = [walk(a, subs) for a in t.args]
        if not any(isinstance(a, Variable) for a in args):
            return t.functor.fn(*args)
        return Term(t.functor, args)
    return t

@dataclass
class Show:
    subs : Subs
    names : dict[Variable, str]
    def __init__(self, subs, names=None):
        self.subs = subs
        if names:
            self.names = names.copy()
        else:
            self.names = dict()

    def __call__(self, t):
        t = walk(t, self.subs)
        if isinstance(t, Variable):
            try:
                return self.names[t]
            except KeyError:
                self.names[t] = n = f"V{len(self.names)}"
                return n
        if isinstance(t, Term):
            args = ", ".join(self(arg) for arg in t.args)
            return f"{t.functor}({args})"
        return repr(t)

class Guard:
    pass

@dataclass
class Eq(Guard):
    a : Expr
    b : Expr
    def __call__(self, env : Env, subs : Subs):
        a = self.a.eva(env, subs)
        b = self.b.eva(env, subs)
        return eq(a, b, subs)

@dataclass
class Op(Guard):
    op : Callable[[Any, Any], Any]
    a : Expr
    b : Expr
    def __call__(self, env : Env, subs : Subs):
        a = self.a.eva(env, subs)
        b = self.b.eva(env, subs)
        return self.op(a, b)

@dataclass
class Decon(Guard):
    functor : Any
    arity : int
    ix : int
    def __call__(self, env : Env, subs : Subs):
        obj = walk(env[ix], subs)
        if isinstance(obj, Term) and obj.functor == self.functor and obj.arity == self.arity:
            for x in reversed(obj.args):
                env.insert(0, x)
            return True
        return False

@dataclass
class CHRStore:
    live : Map[(str, int), Map[CID, None]]
    backlinks : Map[Variable, tuple(CID)]
    history : Map[int, Map[tuple[CID], None]]

    def __iter__(self):
        for group in self.live.values():
            yield from group

    def add(self, name, args):
        cid = CID(name, tuple(args))
        try:
           l = self.live[cid.signature]
        except KeyError:
           l = Map()
        l = l.set(cid, None)
        self.live = self.live.set(cid.signature, l)
        return cid

    def connect(self, var, cid):
        try:
            x = self.backlinks[var] | frozenset([cid])
        except KeyError:
            x = frozenset([cid])
        self.backlinks = self.backlinks.set(var, x)

    def alive(self, cid):
        return cid in self.live[cid.signature]

    def delete(self, cid):
        l = self.live[cid.signature]
        l = l.delete(cid)
        self.live = self.live.set(cid.signature, l)

    def in_history(self, k, ids):
        try:
            hist = self.history[k]
        except KeyError:
            return False
        else:
            return (ids in hist)

    def add_to_history(self, k, ids):
        try:
            hist = self.history[k]
        except KeyError:
            hist = Map()
        hist = hist.set(ids, None)
        self.history = self.history.set(k, hist)

    def lookup(self, sig):
        return list(self.live[sig])

    def occurrences(self, chrp, frame, cid):
        sig = cid.signature
        for k, (_chr, i) in enumerate(chrp.occ.get(sig, ())):
            seq = []
            for j, hsig in enumerate(_chr.head):
                if i == j:
                    seq.append([cid])
                else:
                    seq.append(self.lookup(hsig))
            for ids in itertools.product(*seq):
                if any(not self.alive(i) for i in ids):
                    continue
                if len(set(ids)) != len(ids):
                    continue
                env = sum((list(i.args) for i in ids), [])
                if not self.in_history(k, tuple(ids)):
                    if not all(g(env, frame.subs) for g in _chr.guards):
                        continue
                    self.add_to_history(k, tuple(ids))
                    for j in _chr.deletes:
                        self.delete(ids[j])
                    frame.cont = Cont(frame.cont, env, _chr.goal, pc=0)
        return frame

if __name__=='__main__':
    chrp = CHRProgram([
        CHR([('leq', 2)],
            [Eq(Ix(0), Ix(1))],
            [Success()],
            deletes=(0,)),
        CHR([('leq', 2), ('leq', 2)],
            [Eq(Ix(1), Ix(2)),
             Eq(Ix(0), Ix(3))],
            [Unify(Ix(0), Ix(1)),
             Success()],
            deletes=(0, 1)),
        CHR([('leq', 2), ('leq', 2)],
            [Eq(Ix(1), Ix(2))],
            [Constraint('leq', Ix(0), Ix(3)),
             Success()],
            deletes=()),
        CHR([('leq', 2), ('leq', 2)],
            [Eq(Ix(0), Ix(2)), Eq(Ix(1), Ix(3))],
            [Success()],
            deletes=(1,)),
        
    ])
    module = {
        ("hello", 2): [Unify(Ix(0), Xt("term", Ix(1))), Success()]
    }
    X, Y = Variable(), Variable()
    code = [
        Constraint('leq', Ix(0), Ix(1)),
        Choice(2),
        Invoke("hello", Xt("term", Ix(0)), Ix(1)),
        Success(),
        Unify(Xt("tarm", Ix(1)), Ix(0)),
        Success()
    ]
    stream = Stream(module, chrp, init_frame([X, Y], code))
    for subs, chrs in run(stream):
        show = Show(subs, names = {X: "X", Y: "Y"})
        print("X =", show(X), "; Y =", show(Y))
        for c in chrs:
            print(c.show(show))
