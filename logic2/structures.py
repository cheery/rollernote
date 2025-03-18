from __future__ import annotations
from dataclasses import dataclass
from immutables import Map
from typing import Any

class Variable:
    def __repr__(self):
        return "_"

@dataclass(eq=True, order=True, frozen=True)
class Structure:
    functor : str
    args : tuple[Any]

    @property
    def signature(self):
        return self.functor, len(self.args)

    def show(self, show_fn):
        args = " ".join(map(show_fn, self.args))
        return f"{self.functor} {args}"

    def __repr__(self):
        args = ", ".join(map(repr, self.args))
        return f"{self.functor}({args})"

class Kernel:
    def __init__(self, subs = Map()):
        self.subs = subs

    def bind(self, a, x):
        if self.occurs(a, x):
            return False
        self.subs = self.subs.set(a, x)
        return True

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

def namegen(i=1):
    while True:
        letters = []
        n = i
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            letters.append(chr(65 + remainder))
        yield ''.join(reversed(letters))
        i += 1

@dataclass
class Show:
    names : dict[Variable, str]
    usednames : set[str] = None
    namegen : Any = namegen()
    def __call__(self, x, prec=0):
        if isinstance(x, Variable):
            try:
                return self.names[x]
            except KeyError:
                if self.usednames is None:
                    self.usednames = set(self.names.values())
                self.names[x] = name = next(self.namegen)
                self.usednames.add(name)
                return name
        if isinstance(x, Structure):
            if len(x.args) == 0:
                return x.functor
            elif prec <= 5:
                return x.show(lambda a: self(a, 10))
            else:
                return '(' + self(x) + ')'
        elif isinstance(x, tuple):
            return '{' + ", ".join(self(a, 5) for a in x) + '}'
        else:
            return repr(x)

@dataclass
class Intern:
    intern : dict[str]
    def New(self, name, args):
        if len(args) == 0:
            try:
                return self.intern[name]
            except KeyError:
                self.intern[name] = term = Structure(name, ())
                return term
        else:
            return Structure(name, args)
            
    def __getattr__(self, name):
        def _constructor_(*args):
            return self.New(name, args)
        return _constructor_

term = Intern({})
