"""
    Primitive objects for gui building.
"""
import math
import inspect
import cairo
import cairo_renderer
from contextlib import contextmanager
from contextvars import ContextVar

# Context variable to hold the current composition context
current_composition = ContextVar('current_composition')
ui_memo = ContextVar('ui_memo')
ui = ContextVar('ui')

class Composition:
    """A class to manage the composition and recomposition of composable functions."""
    def __init__(self, parent, key, props, state):
        self.parent = parent
        self.key = key
        self.children = []
        self.props = props
        self.result = None
        self.key_counter = {}
        self.dirty = False
        self.state = state
        self.fresh = True
        # The parts that makes this GUI
        self.drawings = []
        self.listeners = []
        if parent is None or parent.parent is None:
            self.shape = Hit()
        else:
            self.shape = Hidden()

    def memoize(self):
        for child in self.children:
            yield child.key, child

    def set_state(self, key, value):
        self.state[key] = value
        self.set_dirty()

    def set_dirty(self):
        current = self
        while current is not None:
            current.dirty = True
            current = current.parent

    def get_callsite_key(self, depth=2):
        """Generate a unique key for the call site based on the current frame."""
        current_frame = inspect.currentframe()
        if current_frame is None:
            raise RuntimeError("No current frame available")
    
        caller_frame = current_frame
        for i in range(depth):
            if caller_frame is None:
                raise RuntimeError("No caller frame available")
            caller_frame = caller_frame.f_back
        if caller_frame is None:
            raise RuntimeError("No caller frame available")
    
        key = (caller_frame.f_code, caller_frame.f_lineno)
        count = self.key_counter.get(key, 0)
        self.key_counter[key] = count + 1
        return key + (count,)

    def draw(self):
        _ui = ui.get()
        for drawing in self.drawings:
            drawing(_ui, self)
        for children in self.children:
            children.draw()

    def hit(self, x, y):
        if self.shape.test(x, y):
            selection = self
            for child in self.children:
                selection = child.hit(x, y) or selection
            return selection

    def listen(self, event, original=False):
        #key = self.get_callsite_key(2 + depth)
        #print('format', format_key(key))
        def _decorator_(fn):
            #if self.fresh:
            self.listeners.append((event, original, fn))
            #else:
            #    for i, (_, k, _) in enumerate(self.listeners):
            #        print('candinate', format_key(k))
            #        if key == k:
            #            self.listeners[i] = (event, key, fn)
            #            return
            #    assert False, "listener panic"
        return _decorator_

    def preorder(self):
        yield self
        for child in self.children:
            yield from child.preorder()

def get_properties(args, kwargs):
    """Organize the arguments to allow their quick identification"""
    pargs = tuple(sorted(kwargs.items(), key=lambda item: item[0]))
    return (args, pargs)

@contextmanager
def composition_context(comp, memo):
    token0 = current_composition.set(comp)
    token1 = ui_memo.set(memo)
    try:
        yield comp
    finally:
        current_composition.reset(token0)
        ui_memo.reset(token1)

def format_key(key):
    return f"{key[0].co_filename}:{key[1]}"

@contextmanager
def composition_frame(args, kwargs):
    props = get_properties(args, kwargs)
    comp = current_composition.get()
    key = comp.get_callsite_key(4)
    previous = ui_memo.get().get(key)
    if previous is None or previous.props != props or previous.dirty:
        #print(f"{format_key(key)} recomposed")
        this = Composition(comp, key, props, {} if previous is None else previous.state)
        comp.children.append(this)
        with composition_context(this, dict() if previous is None else dict(previous.memoize())):
            assert current_composition.get() == this
            yield this
    else:
        #print(f"{format_key(key)} retained {previous}")
        previous.fresh = False
        previous.parent = comp
        comp.children.append(previous)
        previous.listeners = list(filter(lambda v: v[1], previous.listeners))
        yield previous

def composable(fn):
    def wrapper(*args, **kwargs):
        with composition_frame(args, kwargs) as comp:
            if comp.fresh:
                fn(*args, **kwargs)
            return comp
    return wrapper

class UIState:
    def __init__(self, composition, key):
        self.composition = composition
        self.key = key

    def get_state(self):
        return self.composition.state[self.key]

    def set_state(self, value):
        self.composition.set_state(self.key, value)

    def lazy(self, value):
        old = self.composition.state[self.key]
        self.composition.state[self.key] = value
        if old != value:
            self.composition.set_dirty()

    value = property(get_state, set_state)

def state(initial):
    comp = current_composition.get()
    key = comp.get_callsite_key()
    if key not in comp.state:
        comp.state[key] = initial
    return UIState(comp, key)

class Composer:
    def __init__(self, scene):
        self.scene = scene
        self.composition = Composition(None, None, None, {})

    def __call__(self, *args, **kwargs):
        memo = dict(self.composition.memoize())
        composition = Composition(None, None, None, self.composition.state)
        with composition_context(composition, memo):
            self.scene(*args, **kwargs)
        self.composition = composition
        return composition.dirty

@contextmanager
def ui_context(handle):
    token = ui.set(handle)
    try:
        yield
    finally:
        ui.reset(token)

e_update = object()
e_motion = object()
e_button_down = object()
e_button_up = object()
e_key_down = object()
e_key_up = object()
e_text = object()

keyboad_events = [e_key_down, e_key_up, e_text]

class GUI:
    def __init__(self, widget, scene, *args, **kwargs):
        self.widget = widget
        self.renderer = cairo_renderer.Renderer(widget)
        self.ctx = cairo.Context(self.renderer.surface)
        self.composer = Composer(scene)
        self.args = args
        self.kwargs = kwargs
        self.focus = None
        self.button_presses = {}

    def draw(self):
        with ui_context(self):
            self.widget.exposed = self.widget.exposed or self.composer(*self.args, **self.kwargs)
            self.composer.composition.draw()
        self.renderer.flip()

    def update(self):
        comp = self.composer.composition
        for this in comp.preorder():
            for event, _, handler in this.listeners:
                if event == e_update:
                    handler()
        self.widget.exposed = self.widget.exposed or comp.dirty

    def mouse_motion(self, x, y):
        with ui_context(self):
            comp = self.composer.composition
            this = comp.hit(x, y)
            handled = False
            while this is not None and not handled:
                for event, _, handler in this.listeners:
                    if event == e_motion:
                        handler(x, y)
                        handled = True
                this = this.parent
            self.widget.exposed = self.widget.exposed or comp.dirty

    def mouse_button_down(self, x, y, button):
        with ui_context(self):
            comp = self.composer.composition
            this = comp.hit(x, y)
            handled = False
            while this is not None and not handled:
                for event, _, handler in this.listeners:
                    if event == e_button_down:
                        handler(x, y, button)
                        handled = True
                    if event in keyboad_events:
                        self.focus = this.key
                        this.set_dirty() # Give it chance to react on focus change.
                if handled:
                    self.button_presses[button] = this.key
                this = this.parent
            self.widget.exposed = self.widget.exposed or comp.dirty

    def mouse_button_up(self, x, y, button):
        with ui_context(self):
            comp = self.composer.composition
            key = self.button_presses.pop(button, None)
            for this in comp.preorder():
                if this.key == key:
                    for event, _, handler in this.listeners:
                        if event == e_button_up:
                            handler(x, y, button)
            self.widget.exposed = self.widget.exposed or comp.dirty

    def text_input(self, text):
        with ui_context(self):
            comp = self.composer.composition
            for this in comp.preorder():
                if self.focus == this.key:
                    for event, _, handler in this.listeners:
                        if event == e_text:
                            handler(text)
            self.widget.exposed = self.widget.exposed or comp.dirty

    def key_down(self, sym, repeat, modifiers):
        with ui_context(self):
            comp = self.composer.composition
            for this in comp.preorder():
                if self.focus == this.key:
                    for event, _, handler in this.listeners:
                        if event == e_key_down:
                            handler(sym, repeat, modifiers)
            self.widget.exposed = self.widget.exposed or comp.dirty

    def key_up(self, sym, modifiers):
        with ui_context(self):
            comp = self.composer.composition
            for this in comp.preorder():
                if self.focus == this.key:
                    for event, _, handler in this.listeners:
                        if event == e_key_up:
                            handler(sym, modifiers)
            self.widget.exposed = self.widget.exposed or comp.dirty

    def closing(self):
        return True

    def close(self):
        pass

def drawing(func):
    current_composition.get().drawings.append(func)
    return func

def listen(event):
    return current_composition.get().listen(event, original=True)

def shape(shape):
    current_composition.get().shape = shape

#@contextmanager
def workspace(color=(1,1,1,1), font_family=None):
#    with composition_frame((color, font_family), {}) as comp:
#        if comp.fresh:
            @drawing
            def _workspace_(ui, _):
                ctx = ui.ctx
                if font_family is not None:
                    ctx.select_font_face(font_family)
                ctx.set_source_rgba(*color)
                ctx.rectangle(0, 0, ui.widget.width, ui.widget.height)
                ctx.fill()
#        yield

class Hit:
    def __init__(self, children=None):
        self.children = children or []
        self.on_hover = lambda x, y: None
        self.on_button_down = lambda x, y, button: None
        self.on_button_up = lambda x, y, button: None
    def append(self, item):
        self.children.append(item)

    def extend(self, items):
        self.children.extend(items)

    def hit(self, x, y):
        if self.test(x, y):
            selection = self
            for child in self.children:
                selection = child.hit(x, y) or selection
            return selection

    def trace(self, ctx):
        pass

    def test(self, x, y):
        return True

class Circle(Hit):
    def __init__(self, x, y, radius, children=None):
        super().__init__(children)
        self.x = x
        self.y = y
        self.radius = radius

    def trace(self, ctx):
        #ctx.move_to(self.x + self.radius, self.y)
        ctx.arc(self.x, self.y, self.radius, 0, 2*math.pi)

    def test(self, x, y):
        dx = self.x - x
        dy = self.y - y
        return dx*dx + dy*dy <= self.radius*self.radius

class Box(Hit):
    def __init__(self, x, y, width, height, children=None):
        super().__init__(children)
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def trace(self, ctx):
        ctx.rectangle(self.x, self.y, self.width, self.height)

    def test(self, x, y):
        ix = self.x <= x < self.x + self.width
        iy = self.y <= y < self.y + self.height
        return ix and iy

class Hidden(Hit):
    def __init__(self, children=None):
        super().__init__(children)

    def trace(self, ctx):
        pass

    def test(self, x, y):
        return False
