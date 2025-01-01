# "Deprecating the observer pattern" -paper
import bisect
import random
from collections import namedtuple, deque
from threading import Lock
from weakref import WeakSet

Some = namedtuple('Some', ['value'])

# Engine is an unit holding the flow network together.
class Engine:
    __slots__ = ['observers', 'firing', 'event_lock']
    def __init__(self):
        self.observers = set() # we maintain a list of observers 
                               # to keep them in memory.
        self.firing = dict()
        self.event_lock = Lock()

    # Observers are elements reading the network outwards.
    # Whenever the value signals that it changed, the observer is called.

    # observe is a decorator, eg, you use it like this:
    # @engine.observe(flow1, flow2, ...)
    # def observer(value1, value2, ...)
    #     do things with cell contents.

    # eventually... observer.discard() to discard the observer.

    # If flow is an event, the value is a list of events in the given moment.
    # If flow is a cell, the value is the contents of the cell.

    def observe(self, *sources):
        def _observe_(func):
            return Observer(self, sources, func)
        return _observe_

    # When the engine updates, it step through moments.
    # Every moment is a cycle where the flow network updates itself.
    # On such a cycle, events flow from outward of the network to inside it.

    # engine.send(event, value) sends an event to a moment.
    def send(self, event, value):
        with self.event_lock:
            # A program may send multiple events in one moment.
            if event in self.firing:
                self.firing[event].append(value)
            else:
                self.firing[event] = [value]

    # in some cases observers may feed back event into the network.
    # Roll steps through multiple moments until network has silenced.
    def roll(self):
        while len(self.firing) > 0:
            self.step()

    def step(self):
        # in each moment, the network is computed in
        #   the order of depth from event sources.
        # each flow is visited only once.
        queue = deque()
        visited = set()
        def enqueue(flow):
            if flow not in visited:
                visited.add(flow)
                bisect.insort_right(queue, flow, key=lambda r: r.depth)
        # we collect the currently firing events and prepare
        # the structure to collect events that will fire after this moment.
        with self.event_lock:
            firing, self.firing = self.firing, dict()
        # the dependents of events that are firing in this moment are enqueued
        for event in firing:
            for d in event.dependents:
                enqueue(d)
        while queue:
            flow = queue.popleft()
            if isinstance(flow, Observer):
                assert flow in self.observers, "mixing of flow graphs between engines"
                values = []
                for s in flow.sources:
                    if isinstance(s, Cell):
                        values.append(s.value)
                    else:
                        values.append(firing.get(s, []))
                flow.func(*values)
            # each flow ending up to a queue will get to do a step
            # where it may further enqueue flows and fire.
            elif changed := flow.step(lambda s: firing.get(s, [])):
                if isinstance(flow, Event):
                    assert isinstance(changed, list), flow
                firing[flow] = changed
                for d in flow.dependents:
                    enqueue(d)

# Observers are the outwarding part of the flow network.
# to make them process last, they get the maximum depth.
max_depth = 0xFFFFFFFFFFFFFFFF

class Observer:
    __slots__ = ['engine', 'sources', 'func', 'depth', '__weakref__']
    def __init__(self, engine, sources, func):
        self.engine = engine
        self.sources = sources
        self.func = func
        self.depth = max_depth
        for s in sources:
            s.dependents.add(self)
        self.engine.observers.add(self)

    def discard(self):
        self.engine.observers.discard(self)
        # the observer is disconnected
        # so that it won't fire after discarded.
        for source in self.sources:
            source.dependents.discard(self)

# Flows are the nodes of the reaction network.
# Whenever a flow gets created, it starts interacting in the network.
class Flow:
    __slots__ = ['sources', 'dependents', 'depth', '__weakref__']
    def __init__(self, sources=None):
        self.sources = [] if sources is None else sources
        self.dependents = WeakSet()
        for s in self.sources:
            s.dependents.add(self)
        self.depth = 0
        self.redepth()

    # Depth is used to determine which flow nodes need to be updated
    # before we allow this flow node to step.

    # Depth may need to be recalculated if network structure changes.
    # Whenever that happens, it cascades through the network in order
    # to produce new depth values.
    def redepth(self):
        depth = 0 if len(self.sources) == 0 else 1 + max(s.depth for s in self.sources)
        if self.depth != depth:
            self.depth = depth
            for d in self.dependents:
                if isinstance(d, Flow):
                    d.redepth()

    def step(self, get):
        return False

# Events are flows that may fire occassionally.
# Whenever they fire, they transmit a value.
class Event(Flow):
    __slots__ = []

# Eg, you might have an event that describes a pulse or a "heartbeat".
# --1--2--3--4--5--6--7-->

# Sources are events that come from outside the network.
class Source(Event):
    __slots__ = ['engine']
    def __init__(self, engine):
        self.engine = engine
        super().__init__()

    def fire(self, value):
        self.engine.send(self, value)

# Never is an event that never fires.
# eg. It is...
# ----------------------->
never = Event()

# Merging of two events combine the occurences into one.
# eg. input events:
# --*-----*---*---------->
# -----*----------------->
# result:
# --*--*--*---*---------->

# Now there's a question of what should happen whenever we merge events
# that occur simultaneously?
# Our answer is to interleave them randomly.
# This is somewhat unsatisfactory answer but well.. it's ok for now.
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

    def step(self, get):
        x, y = self.sources
        return self.func(get(x), get(y))

# Events may snapshot values from multiple cells.
class Snapshot(Event):
    __slots__ = ['func']
    def __init__(self, func, event, *sources):
        super().__init__([event] + list(sources))
        self.func = func

    def step(self, get):
        event = self.sources[0]
        if occ := get(event):
            snap = [s.value for s in self.sources[1:]]
            return [self.func(v, *snap) for v in occ]

# @snapshot(event, cell1, cell2, cell3...)
# def _flow_name_(value0, value1, value2, value3...):
#     return ...
def snapshot(event, *cells):
    def _decorator_(func):
        return Snapshot(func,  event, *cells)
    return _decorator_

# Collect is a combined filter+map for events.
# The function returns Some(v) if the occurence
# of the event is preserved, None otherwise.
class Collect(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        occ = []
        for v in get(event):
            match self.func(v):
                case Some(a):
                    occ.append(a)
                case _:
                    pass
        return occ

# @collect(event)
# def _flow_name_(value):
#     if ...:
#         return Some(value)
#     else:
#         return None
def collect(event):
    def _decorator_(func):
        return Collect(func,  event)
    return _decorator_
    
# MapE changes the content of the event somehow.
class MapE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        return [self.func(v) for v in get(event)]

# @mapE(event)
# def _flow_name_(value):
#     return new_value
def mapE(event):
    def _decorator_(func):
        return MapE(func,  event)
    return _decorator_

# Filter includes or drops an event according to it's content.
class FilterE(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        return [v for v in get(event) if self.func(v)]

# @filterE(event)
# def _flow_name_(value):
#     return True or False
def filterE(event):
    def _decorator_(func):
        return FilterE(func,  event)
    return _decorator_

# Expand expands a single event into multiple events.
class Expand(Event):
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        occ = []
        for v in get(event):
            occ.extend(self.func(v))
        return occ

# @expandE(event)
# def _flow_name_(value):
#     return [values...]
def expandE(event):
    def _decorator_(func):
        return ExpandE(func,  event)
    return _decorator_

# Cells are flow nodes that represent values changing over time.
class Cell(Flow):
    __slots__ = ['value']
    def __init__(self, initial, sources):
        super().__init__(sources)
        self.value = initial

    def step(self, get):
        return True

# Hold is the simplest cell. Whenever an event occurs,
# it changes to the content of the occurence of the event.
class Hold(Cell):
    __slots__ = []
    def __init__(self, initial, event=never):
        assert isinstance(event, Event)
        super().__init__(initial, [event])

    def step(self, get):
        self.value = get(self.sources[0])[-1]
        return True

# Memory adds a function to the cell.
class Memory(Cell):
    __slots__ = ['func']
    def __init__(self, initial, func, event):
        assert isinstance(event, Event)
        super().__init__(initial, [event])
        self.func = func

    def step(self, get):
        for value in get(self.sources[0]):
            self.value = self.func(self.value, value)
        return True

# @memory(initial, event)
# def _flow_name_(prev_value, occurence):
#     return new_value
def memory(initial, event):
    def _decorator_(func):
        return Memory(initial, func, event)
    return _decorator_

# Accum is like the memory cell,
# but functions the same with a cell that has its contents updated.
class Accum(Cell):
    __slots__ = ['func']
    def __init__(self, initial, func, source):
        assert isinstance(source, Cell)
        super().__init__(initial, [source])
        self.func = func

    def step(self, get):
        self.value = self.func(self.value, self.sources[0].value)
        return True

# @accum(initial, cell)
# def _flow_name_(prev_value, occurence):
#     return new_value
def accum(initial, cell):
    def _decorator_(func):
        return Accum(initial, func, cell)
    return _decorator_

# Compute gets its value from other cells.
class Compute(Cell):
    __slots__ = ['func']
    def __init__(self, func, sources):
        initial = func(*(s.value for s in sources))
        super().__init__(initial, sources)
        self.func = func

    def step(self, get):
        self.value = self.func(*(s.value for s in self.sources))
        return True

# @compute(cell1, cell2, ...)
# def _flow_name_(value1, value2, ...)
#     return new_value
def compute(*cells):
    def _decorator_(func):
        return Compute(func, cells)
    return _decorator_

# Changes is an event that observes a cell.
# whenever the value changes in that cell, it fires
# with (previous_value, current_value)
class Changes(Event):
    def __init__(self, source):
        self.prev_value = source.value
        super().__init__([source])

    def step(self, get):
        prev = self.prev_value
        self.prev_value = current = self.sources[0].value
        if current != prev:
            return [(prev, current)]

# These two remaining implementations are a bit questionable.
# Should we observe which value when the cell contents change?

# Switch takes a cell containing events and transmits messages of that event.
class Switch(Event):
    __slots__ = []
    def __init__(self, cell):
        super().__init__([cell, cell.value])

    def step(self, get):
        event, current = self.sources
        if upcoming := get(event):
            current.dependents.discard(self)
            upcoming.dependents.add(self)
            self.sources[1] = upcoming
            self.redepth()
        return get(current)

# Join merges nested cells into one.
class Join(Cell):
    __slots__ = []
    def __init__(self, supercell):
        super().__init__(supercell.value.value, [supercell, supercell.value])

    def step(self, get):
        supercell, current = self.sources
        if get(supercell):
            current.dependents.discard(self)
            supercell.value.dependents.add(self)
            self.sources[1] = supercell.value
            self.redepth()
        self.value = current.value
        return get(current)
