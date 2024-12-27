# "Deprecating the observer pattern" -paper
import bisect
from contextvars import ContextVar
from collections import namedtuple, deque

Some = namedtuple('Some', ['value'])

class Engine:
    __slots__ = ['sinks', 'firing']
    def __init__(self):
        self.sinks = set()
        self.firing = {}

    def observe(self, flow):
        def _observe_(func):
            sink = Sink(self, flow, func)
            flow.connect(sink)
            self.sinks.add(sink)
            return sink
        return _observe_

    def send(self, event, value):
        self.firing[event] = Some(value)

    def step(self):
        queue = deque()
        visited = set()
        def enqueue(reactive):
            if reactive not in visited:
                visited.add(reactive)
                reactive.relevel()
                bisect.insort_right(queue, reactive, key=lambda r: r.level)
        firing = self.firing.copy()
        for event in self.firing:
            enqueue(event)
        self.firing.clear()
        out = []
        while queue:
            reactive = queue.popleft()
            if isinstance(reactive, Sink):
                out.append(reactive)
            else:
                reactive.step(enqueue, firing)
        for sink in out:
            sink.func(firing[sink.source].value)

class Sink:
    __slots__ = ['engine', 'source', 'func', 'level']
    def __init__(self, engine, source, func):
        self.engine = engine
        self.source = source
        self.func = func

    def relevel(self):
        self.level = self.source.level

    def discard(self):
        engine.sinks.discard(self)
        self.source.discard(self)

class Flow:
    __slots__ = ['sources', 'dependents', 'level']
    def __init__(self, sources=None):
        self.sources = [] if sources is None else sources
        self.dependents = set()

    def relevel(self):
        self.level = 0 if len(self.sources) == 0 else 1 + max(s.level for s in self.sources)

    def connect(self, dependent):
        self.dependents.add(dependent)
        if len(self.dependents) == 1:
            for source in self.sources:
                source.connect(self)

    def discard(self, dependent):
        self.sinks.discard(dependent)
        if len(self.dependents) == 0:
            for source in self.sources:
                source.discard(self)

    def step(self, enqueue, firing):
        for dependent in self.dependents:
            enqueue(dependent)

class Event(Flow):
    __slots__ = []

never = Event()

class Merge(Event):
    __slots__ = ['func']
    def __init__(self, func, x, y):
        super().__init__([x, y])
        self.func = func

    def step(self, enqueue, firing):
        x, y = self.sources
        firing[self] = Some(self.func(self.x.get(firing), self.y.get(firing)))
        super().step(enqueue, firing)

class MapE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        firing[self] = Some(self.func(firing[event]))
        super().step(enqueue, firing)

class FilterE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        result = self.func(firing[event])
        if isinstance(result, Some):
            firing[self] = result
            super().step(enqueue, firing)

class Cell(Flow):
    __slots__ = ['value']
    def __init__(self, initial, sources):
        super().__init__(sources)
        self.value = initial

    def step(self, enqueue, firing):
        firing[self] = Some(self.value)
        super().step(enqueue, firing)

class Hold(Cell):
    __slots__ = []
    def __init__(self, initial, event):
        super().__init__(initial, [event])

    def step(self, enqueue, firing):
        self.value = firing[self.sources[0]].value
        super().step(enqueue, firing)

class Compute(Cell):
    __slots__ = ['func']
    def __init__(self, func, sources):
        initial = func(*(s.value for s in sources))
        super().__init__(initial, sources)
        self.func = func

    def step(self, enqueue, firing):
        self.value = self.func(*(s.value for s in self.sources))
        super().step(enqueue, firing)

class Switch(Event):
    __slots__ = []
    def __init__(self, cell):
        super().__init__([cell, cell.value])

    def step(self, enqueue, firing):
        event, current = self.sources
        match firing.get(event):
            case Some(upcoming):
                 current.discard(self)
                 upcoming.connect(self)
                 self.sources[1] = upcoming
            case _:
                 pass
        match firing.get(current):
            case Some(_) as v:
                 firing[self] = v
                 super().step(enqueue, firing)
            case _:
                 pass

class Join(Cell):
    __slots__ = []
    def __init__(self, supercell):
        super().__init__(supercell.value.value, [supercell, supercell.value])

    def step(self, enqueue, firing):
        supercell, current = self.sources
        if supercell in firing:
            current.discard(self)
            supercell.value.connect(self)
            self.sources[1] = supercell.value
        if current in firing:
            self.value = current.value
            super().step(enqueue, firing)
