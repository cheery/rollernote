# "Deprecating the observer pattern" -paper
import bisect
import random
from contextvars import ContextVar
from collections import namedtuple, deque

Some = namedtuple('Some', ['value'])

class Engine:
    __slots__ = ['sinks', 'firing']
    def __init__(self):
        self.sinks = set()
        self.firing = {}

    def observe(self, *flows):
        def _observe_(func):
            sink = Sink(self, flows, func)
            for flow in flows:
                flow.connect(sink)
            self.sinks.add(sink)
            return sink
        return _observe_

    def send(self, event, value):
        if event in self.firing:
            self.firing[event].append(value)
        else:
            self.firing[event] = [value]

    def roll(self):
        while len(self.firing) > 0:
            self.step()

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
            results = []
            for s in sink.sources:
                if isinstance(s, Cell):
                    results.append(s.value)
                else:
                    results.append(firing.get(s, []))
            sink.func(*results)

class Sink:
    __slots__ = ['engine', 'sources', 'func', 'level']
    def __init__(self, engine, sources, func):
        self.engine = engine
        self.sources = sources
        self.func = func

    def relevel(self):
        self.level = max(s.level for s in self.sources) + 1

    def discard(self):
        self.engine.sinks.discard(self)
        for source in self.sources:
            source.discard(self)

class Flow:
    __slots__ = ['sources', 'dependents', 'level']
    def __init__(self, sources=None):
        self.sources = [] if sources is None else sources
        self.dependents = set()
        self.relevel()

    def relevel(self):
        self.level = 0 if len(self.sources) == 0 else 1 + max(s.level for s in self.sources)

    def connect(self, dependent):
        self.dependents.add(dependent)
        if len(self.dependents) == 1:
            for source in self.sources:
                source.connect(self)

    def discard(self, dependent):
        self.dependents.discard(dependent)
        if len(self.dependents) == 0:
            for source in self.sources:
                source.discard(self)

    def step(self, enqueue, firing):
        for dependent in self.dependents:
            enqueue(dependent)

class Event(Flow):
    __slots__ = []

never = Event()

def merge_nondet(xs, ys):
    merged = []
    i, j = 0, 0
    while i < len(xs) and j < len(ys):
        if random.choice([False,True]):
            merged.append(xs[i])
            i += 1
        else:
            merged.append(ys[j])
            j += 1
    return merged + xs[i:] + ys[j:]

class Merge(Event):
    __slots__ = ['func']
    def __init__(self, x, y, func=merge_nondet):
        super().__init__([x, y])
        self.func = func

    def step(self, enqueue, firing):
        x, y = self.sources
        firing[self] = self.func(firing.get(x, []), firing.get(y, []))
        super().step(enqueue, firing)

class Snapshot(Event):
    __slots__ = ['func']
    def __init__(self, func, event, *sources):
        super().__init__([event] + list(sources))
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        if event in firing:
            snap = [s.value for s in self.sources[1:]]
            firing[self] = [self.func(v, *snap) for v in firing[event]]
            super().step(enqueue, firing)

class Collect(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        result = []
        for v in firing[event]:
            match self.func(v):
                case Some(a):
                    result.append(a)
                case _:
                    pass
        if len(result) > 0:
            firing[self] = result
            super().step(enqueue, firing)

class MapE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        firing[self] = [self.func(v) for v in firing[event]]
        super().step(enqueue, firing)

class FilterE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        result = [v for v in firing[event] if self.func(v)]
        if len(result) > 0:
            firing[self] = result
            super().step(enqueue, firing)

class Expand(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, enqueue, firing):
        event = self.sources[0]
        result = []
        for v in firing[event]:
            result.extend(self.func(v))
        if len(result) > 0:
            firing[self] = result
            super().step(enqueue, firing)

class Cell(Flow):
    __slots__ = ['value']
    def __init__(self, initial, sources):
        super().__init__(sources)
        self.value = initial

    def step(self, enqueue, firing):
        firing[self] = None
        super().step(enqueue, firing)

class Hold(Cell):
    __slots__ = []
    def __init__(self, initial, event=never):
        super().__init__(initial, [event])

    def step(self, enqueue, firing):
        self.value = firing[self.sources[0]][-1]
        super().step(enqueue, firing)

class Memory(Cell):
    __slots__ = ['func']
    def __init__(self, initial, func, event):
        super().__init__(initial, [event])
        self.func = func

    def step(self, enqueue, firing):
        for value in firing[self.sources[0]]:
            self.value = self.func(self.value, value)
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

class Changes(Event):
    def __init__(self, source):
        self.prev_value = source.value
        super().__init__([source])

    def step(self, enqueue, firing):
        prev = self.prev_value
        self.prev_value = current = self.sources[0].value
        if current != prev:
            firing[self] = [(prev, current)]
            super().step(enqueue, firing)

class Switch(Event):
    __slots__ = []
    def __init__(self, cell):
        super().__init__([cell, cell.value])

    def step(self, enqueue, firing):
        event, current = self.sources
        if upcoming := firing.get(event):
            current.discard(self)
            upcoming.connect(self)
            self.sources[1] = upcoming
        if vs := firing.get(current):
            firing[self] = vs
            super().step(enqueue, firing)

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
