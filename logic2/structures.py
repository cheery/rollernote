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
            if prec <= 0:
                return ", ".join(self(a, 5) for a in x)
            else:
                return '(' + self(x) + ')'
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
