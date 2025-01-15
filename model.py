from typing import get_type_hints
from weakref import WeakSet
from inspect import Signature, Parameter

class bind:
    __fields__ = ['model', 'attr']
    def __init__(self, model, attr):
        assert attr in model._fields
        self.model = model
        self.attr = attr

    @property
    def value(self):
        return getattr(self.model, self.attr)

    @value.setter
    def value(self, value):
        return setattr(self.model, self.attr, value)

    @property
    def version(self):
        return self.model.version
        
class MetaModel(type):
    def __new__(cls, name, bases, dct):
        ty = super().__new__(cls, name, bases, dct)
        ty._types = get_type_hints(ty)
        for name, that in ty._types.items():
            setattr(ty, name, Field(name, that))
        parameters = [Parameter(name, Parameter.POSITIONAL_OR_KEYWORD) for name in ty._types]
        ty._signature = Signature(parameters)
        return ty

class Field:
    def __init__(self, name, ty):
        self.name = name
        self.ty = ty

    def __get__(self, model):
        return self.model._fields[self.name]

    def __set__(self, model, value):
        previous = model._fields[self.name]
        if isinstance(previous, Model):
            previous.super.discard(model)
        if not isinstance(value, self.ty):
            raise TypeError(f".{self.name} must be of type {ty}")
        if isinstance(value, Model):
            value.super.add(model)
        model._fields[self.name] = value
        model.notify()

class Model(metaclass=MetaModel):
    __fields__ = ['super', 'version', '_fields', '__weakref__']
    def __init__(self, *args, **kwargs):
        self.super = WeakSet()
        self.version = 0
        self._fields = self._signature.bind(*args, **kwargs).arguments
        for name, ty in self._types.items():
            value = self._fields[name]
            if not isinstance(value, ty):
                raise TypeError(f".{name} must be of type {ty}")
            if isinstance(value, Model):
                value.super.add(self)

    def __setattr__(self, name, value):
        return super().__setattr__(name, value)
        if name in self._fields:
            return

    def notify(self):
        self.version += 1
        for sup in self.super:
            sup.notify()
