"""
    Functional reactive programming for python.

    Implementation is from
    "Deprecating the observer pattern" -paper
"""
import bisect
import random
from collections import namedtuple, deque
from threading import Lock
from weakref import WeakSet

Some = namedtuple('Some', ['value'])

def query(primed, event):
    try:
        return Some(primed[event])
    except KeyError:
        return None

class FlowChanged(Exception):
    """
    Sometimes the flow network changes such that
    it needs a new topological sort.

    In that case the Flow.step -function must raise FlowChanged
    until the engine resolves the problem.
    """

class Engine:
    __slots__ = {
        'observers': "observers listening the flow network, bookkeeping to keep them from being garbage collected.",
        'primed': "events primed for the next moment",
        'event_lock': "lock that is engaged when modifying 'primed'",
    }
    def __init__(self):
        self.observers = set()
        self.primed = dict()
        self.event_lock = Lock()

    def observe(self, *sources):
        """
        Observers are elements reading the network outwards.
        Whenever the value signals that it changed, the observer is called.

        observe is a decorator, eg, you use it like this:
        @engine.observe(flow1, flow2, ...)
        def observer(value1, value2, ...)
            do things with cell contents.

        # If flow is an event, the value is None/Some(value) in the given moment.
        # If flow is a cell, the value is the contents of the cell.

        eventually... observer.discard() to discard the observer.
        """
        def _observe_(func):
            return Observer(self, sources, func)
        return _observe_

    def send(self, event, value, evolve=lambda _, v: v):
        """
        Primes an event to be sent on the next moment.

        Only one event can be sent at each moment.

        To make it easier to maintain event flow with one event,
        the user may supply an 'evolve' -function that gets
        None/Some(previous_value) and the value user passed in.
        """
        with self.event_lock:
            prior = query(self.primed, event)
            self.primed[event] = evolve(prior, value)

    def roll(self):
        """
        In some use cases observers may feed events back into the network.
        Roll steps through multiple moments until network has silenced.
        """
        while len(self.primed) > 0:
            self.step()

    def step(self):
        """
        When the engine updates, it steps through moments.
        Every moment flow network updates itself.
        On such a moment, events flow from outward of the network to inside it.

        In each moment, the network is topologically sorted with depth
        from event sources and primed parts of the network
        are stepped through in that order.

        The events primed to fire in current moment are collected
        and form the basis for the current moment's flow network update.

        Dependents of each event source are enqueued.

        Each flow ending up to a queue will get to do a step
        where it may prime and send it's dependents to the queue.

        primed -dictionary holds None/Some(value) for events
        and 'True' for primed cells.
        """
        queue = deque()
        visited = set()
        def enqueue(flow, retry=False):
            if flow not in visited or retry:
                visited.add(flow)
                bisect.insort_right(queue, flow, key=lambda r: r.depth)
        with self.event_lock:
            primed, self.primed = self.primed, dict()
        for event in primed:
            for d in event.dependents:
                enqueue(d)
        while queue:
            flow = queue.popleft()
            if isinstance(flow, Observer):
                assert flow.engine is self, "mixing of flow graphs between engines"
                values = []
                for s in flow.sources:
                    if isinstance(s, Cell):
                        values.append(s.value)
                    else:
                        values.append(primed.get(s))
                flow.func(*values)
            else:
                try:
                    if changed := flow.step(lambda s: query(primed, s)):
                        primed[flow] = changed.value
                        for d in flow.dependents:
                            enqueue(d)
                except FlowChanged:
                    primed[flow] = None
                    flow.redepth()
                    queue = deque(sorted(queue, key=lambda r: r.depth))
                    enqueue(flow, retry=True)

# Observers are the outwarding part of the flow network.
# to make them process last, they get the maximum depth.
max_depth = 0xFFFFFFFFFFFFFFFF

class Observer:
    __slots__ = ['engine', 'sources', 'func', 'depth', '__weakref__']
    def __init__(self, engine, sources, func):
        """
        Construct through the engine.observe -decorator.
        """
        self.engine = engine
        self.sources = sources
        self.func = func
        self.depth = max_depth
        for s in sources:
            s.dependents.add(self)
        self.engine.observers.add(self)

    def discard(self):
        """
        When you want that the observer stops observing, you need to explicitly tell so.

        The observer is disconnected so that it won't prime after being discarded.
        """
        self.engine.observers.discard(self)
        for source in self.sources:
            source.dependents.discard(self)

class Flow:
    """
    Flows are the nodes of the reaction network.
    Whenever a flow gets created, it starts interacting in the network.
    """
    __slots__ = ['sources', 'dependents', 'depth', '__weakref__']
    def __init__(self, sources=None):
        self.sources = [] if sources is None else sources
        self.dependents = WeakSet()
        for s in self.sources:
            s.dependents.add(self)
        self.depth = 0
        self.redepth()

    def stale(self):
        """
        Internal function used to determine whether .redepth should be invoked.
        """
        depth = 0 if len(self.sources) == 0 else 1 + max(s.depth for s in self.sources)
        return self.depth != depth

    def redepth(self):
        """
        Depth is used to determine which flow nodes need to be updated
        before we allow this flow node to step.

        Depth may need to be recalculated if network structure changes.
        Whenever that happens, it cascades through the network in order
        to produce new depth values.
        """
        self.depth = 0 if len(self.sources) == 0 else 1 + max(s.depth for s in self.sources)
        for d in self.dependents:
            if isinstance(d, Flow):
                d.redepth()

    def step(self, get):
        """
        Function to be implemented by events and cells.

        'get' is there to get a value of the event in the current moment.
        eg. None/Some(value)
        
        step is supposed to return a None/Some(value).

        The truth value of the output will tell
        whether dependents of the cell should be primed as well.
        """
        return None

class Event(Flow):
    """
    Events are flows that may occur occassionally, but only once in each moment.
    Whenever event is primed, it transmits a value.

    Eg, you might have an event that describes a pulse or a "heartbeat".
    --1--2--3--4--5--6--7-->
    """
    __slots__ = []

class Source(Event):
    """
    Sources are events that come from outside of the network.
    """
    __slots__ = ['engine']
    def __init__(self, engine):
        self.engine = engine
        super().__init__()

    def send(self, value, evolve=lambda _, v: v):
        """
        Calls Engine.send with this event.
        """
        self.engine.send(self, value, evolve)

never = Event()
"""
    Never is an event that never fires.
    eg. It is...
    ----------------------->
"""

class Merge(Event):
    """
    Merging of two events combine the occurences into one.
    The results depend on how we combine them.

    func gets pair of None/Some(x)
    """
    __slots__ = ['func']
    def __init__(self, x, y, func):
        super().__init__([x, y])
        self.func = func

    def step(self, get):
        x, y = self.sources
        return self.func(get(x), get(y))

class Snapshot(Event):
    """
    Events may snapshot values from multiple cells.
    """
    __slots__ = ['func']
    def __init__(self, func, event, *sources):
        super().__init__([event] + list(sources))
        self.func = func

    def step(self, get):
        event = self.sources[0]
        if occ := get(event):
            snap = [s.value for s in self.sources[1:]]
            return Some(self.func(occ.value, *snap))

def snapshot(event, *cells):
    """
    @snapshot(event, cell1, cell2, cell3...)
    def _flow_name_(value0, value1, value2, value3...):
        return ...
    """
    def _decorator_(func):
        return Snapshot(func,  event, *cells)
    return _decorator_

class Collect(Event):
    """
    Collect is a combined filter+map for events.
    The function returns Some(v) if the occurence
    of the event is preserved, None otherwise.
    """
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        return self.func(get(event).value)

def collect(event):
    """
    @collect(event)
    def _flow_name_(value):
        if ...:
            return Some(value)
        else:
            return None
    """
    def _decorator_(func):
        return Collect(func,  event)
    return _decorator_
    
class MapE(Event):
    """MapE changes the content of the event."""
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        return Some(self.func(get(event).value))

def mapE(event):
    """
    @mapE(event)
    def _flow_name_(value):
        return new_value
    """
    def _decorator_(func):
        return MapE(func,  event)
    return _decorator_

class FilterE(Event):
    """ Filter includes or drops an event according to it's content."""
    __slots__ = ['func']
    def __init__(self, func, event):
        super().__init__([event])
        self.func = func

    def step(self, get):
        event = self.sources[0]
        occ = get(event)
        if self.func(occ.value):
            return occ

def filterE(event):
    """
    @filterE(event)
    def _flow_name_(value):
        return True or False
    """
    def _decorator_(func):
        return FilterE(func,  event)
    return _decorator_

class Cell(Flow):
    """Cells are flow nodes that represent values changing over time."""
    __slots__ = ['value']
    def __init__(self, initial, sources):
        super().__init__(sources)
        self.value = initial

class Hold(Cell):
    """
    Hold is the simplest cell. Whenever an event occurs,
    it changes to the content of the occurence of the event.
    """
    __slots__ = []
    def __init__(self, initial, event=never):
        assert isinstance(event, Event)
        super().__init__(initial, [event])

    def step(self, get):
        self.value = get(self.sources[0]).value
        return Some(None)

class Memory(Cell):
    """Memory adds a function to the cell."""
    __slots__ = ['func']
    def __init__(self, initial, func, event):
        assert isinstance(event, Event)
        super().__init__(initial, [event])
        self.func = func

    def step(self, get):
        self.value = self.func(self.value, get(self.sources[0]).value)
        return Some(None)

def memory(initial, event):
    """
    @memory(initial, event)
    def _flow_name_(prev_value, occurence):
        return new_value
    """
    def _decorator_(func):
        return Memory(initial, func, event)
    return _decorator_

class Accum(Cell):
    """
    Adds a function to the cell, but uses it to compute values from other cells.
    """
    __slots__ = ['func']
    def __init__(self, initial, func, sources):
        super().__init__(initial, sources)
        self.func = func

    def step(self, get):
        self.value = self.func(self.value, *(s.value for s in self.sources))
        return Some(None)

def accum(initial, *cells):
    """
    @accum(initial, cell1, cell2, ...)
    def _flow_name_(prev_value, value1, value2, ...):
        return new_value
    """
    def _decorator_(func):
        return Accum(initial, func, cells)
    return _decorator_

class Compute(Cell):
    """Compute gets its value from other cells."""
    __slots__ = ['func']
    def __init__(self, func, sources):
        initial = func(*(s.value for s in sources))
        super().__init__(initial, sources)
        self.func = func

    def step(self, get):
        self.value = self.func(*(s.value for s in self.sources))
        return Some(None)

def compute(*cells):
    """
    @compute(cell1, cell2, ...)
    def _flow_name_(value1, value2, ...)
        return new_value
    """
    def _decorator_(func):
        return Compute(func, cells)
    return _decorator_

class Changes(Event):
    """
    Changes is an event that observes a cell.
    whenever the value changes in that cell, it fires
    with (previous_value, current_value)
    """
    def __init__(self, source):
        self.prev_value = source.value
        super().__init__([source])

    def step(self, get):
        prev = self.prev_value
        self.prev_value = current = self.sources[0].value
        if current != prev:
            return Some((prev, current))

class Join(Cell):
    """Join merges nested cells into one."""
    __slots__ = []
    def __init__(self, supercell):
        super().__init__(supercell.value.value, [supercell, supercell.value])
 
    def step(self, get):
        supercell, current = self.sources
        if supercell.value != current:
            current.dependents.discard(self)
            supercell.value.dependents.add(self)
            self.sources[1] = current = supercell.value
            if self.stale():
                raise FlowChanged()
        self.value = current.value
        return get(current) or get(self)
