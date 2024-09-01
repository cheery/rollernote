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

identity_transform = cairo.Matrix()

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
        self.post_drawings = []
        self.listeners = []
        self.layout = None
        self.transform = identity_transform
        self.clipping = False
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

    def get_callsite_key(self, fn, depth=2):
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
    
        key = (fn, caller_frame.f_code, caller_frame.f_lineno)
        count = self.key_counter.get(key, 0)
        self.key_counter[key] = count + 1
        return key + (count,)

    def draw(self):
        _ui = ui.get()
        _ui.ctx.save()
        try:
            if self.clipping:
                self.shape.trace(_ui.ctx)
                _ui.ctx.clip()
            _ui.ctx.transform(self.transform)
            for drawing in self.drawings:
                drawing(_ui, self)
            for children in self.children:
                children.draw()
            for drawing in self.post_drawings:
                drawing(_ui, self)
        finally:
            _ui.ctx.restore()

    def hit(self, x, y):
        if self.shape.test(x, y):
            matrix = cairo.Matrix(*self.transform)
            matrix.invert()
            x, y = matrix.transform_point(x, y)
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
            return fn
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
    return f"{key[1].co_filename}:{key[2]}"

def memoize(previous):
    return dict() if previous is None else dict(previous.memoize())

@contextmanager
def composition_frame(fn, args, kwargs, d=0):
    props = get_properties(args, kwargs)
    comp = current_composition.get()
    key = comp.get_callsite_key(fn, 4+d)
    previous = ui_memo.get().get(key)
    if previous is None or previous.props != props or previous.dirty:
        #print(f"{format_key(key)} recomposed")
        state = {} if previous is None else previous.state
        this = Composition(comp, key, props, state)
        comp.children.append(this)
        with composition_context(this, memoize(previous)):
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
        with composition_frame(fn, args, kwargs) as comp:
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
    key = comp.get_callsite_key(None)
    if key not in comp.state:
        comp.state[key] = initial
    return UIState(comp, key)

class UIStateBundle:
    __slots__ = ['_composition', '_key', '_lazy']
    def __init__(self, _composition, _key, _lazy):
        self._composition = _composition
        self._key = _key
        self._lazy = _lazy

    def __getattr__(self, name):
        try:
            return self._composition.state[self._key][name]
        except KeyError:
            raise AttributeError

    def __setattr__(self, name, value):
        try:
            super().__setattr__(name, value)
        except AttributeError:
            bundle = self._composition.state[self._key]
            try:
                old = bundle[name]
                bundle[name] = value
                if not self._lazy or old != value:
                   self._composition.set_dirty()
            except KeyError:
                raise AttributeError

def bundle(**kwargs):
    comp = current_composition.get()
    key = comp.get_callsite_key(None)
    if key not in comp.state:
        comp.state[key] = kwargs
    return UIStateBundle(comp, key, False)

def lazybundle(**kwargs):
    comp = current_composition.get()
    key = comp.get_callsite_key(None)
    if key not in comp.state:
        comp.state[key] = kwargs
    return UIStateBundle(comp, key, True)

def setter(bundle, name):
    return lambda value: setattr(bundle, name, value)

class Composer:
    def __init__(self, scene):
        self.scene = scene
        self.composition = Composition(None, None, None, {})
        self.composition.layout = DynamicLayout(flexible_width=True, flexible_height=True)

    def __call__(self, *args, **kwargs):
        memo = dict(self.composition.memoize())
        composition = Composition(None, None, None, self.composition.state)
        composition.layout = DynamicLayout(flexible_width=True, flexible_height=True)
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
e_entering = object()
e_dragging = object()
e_leaving = object()
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
        self.under_motion = None

    def draw(self):
        with ui_context(self):
            self.widget.exposed = self.widget.exposed or self.composer(*self.args, **self.kwargs)
            comp = self.composer.composition
            comp.layout.measure(comp.children, self.widget.width, self.widget.height)
            if comp.layout is not None:
                shape = Box(0, 0, comp.layout.width, comp.layout.height)
                comp.layout(comp, shape)
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
            handled_by = None
            if len(self.button_presses) > 0 and self.under_motion is not None:
                for that in comp.preorder():
                    if that.key == self.under_motion:
                        for event, _, handler in that.listeners:
                            if event == e_dragging:
                                handler(x,y)
                                handled_by = that.key
            while this is not None and handled_by is None:
                if this.key != self.under_motion:
                    for event, _, handler in this.listeners:
                        if event == e_entering:
                            handler(x, y)
                            handled_by = this.key
                if handled_by is None:
                    for event, _, handler in this.listeners:
                        if event == e_entering:
                            handled_by = this
                        elif event == e_motion:
                            handler(x, y)
                            handled_by = this.key
                this = this.parent
            if handled_by != self.under_motion and self.under_motion is not None:
                for that in comp.preorder():
                    if that.key == self.under_motion:
                        for event, _, handler in that.listeners:
                            if event == e_leaving:
                                handler(x,y)
            self.under_motion = handled_by
        self.widget.exposed = self.widget.exposed or comp.dirty

    def mouse_button_down(self, x, y, button):
        with ui_context(self):
            comp = self.composer.composition
            this = comp.hit(x, y)
            handled_by = None
            focus_by = None
            while this is not None and (handled_by is None or focus_by is None):
                for event, _, handler in this.listeners:
                    if event == e_button_down and (handled_by is None or handled_by == this.key):
                        handler(x, y, button)
                        handled_by = this.key
                    if event in keyboad_events and (focus_by is None or focus_by == this.key):
                        this.set_dirty() # Give it chance to react on focus change.
                        focus_by = this.key
                this = this.parent
            if handled_by is not None:
                self.button_presses[button] = handled_by
            if focus_by is not None:
                self.focus = focus_by
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

    # We assume we're in custom context.
    def custom_global_event(self, e_event, *args):
        comp = self.composer.composition
        for this in comp.preorder():
            for event, _, handler in this.listeners:
                if event == e_event:
                    handler(*args)

    def custom_event(self, e_event, this, *args):
        handled_by = None
        while this is not None and handled_by is None:
            for event, _, handler in this.listeners:
                if event == e_event:
                    handler(*args)
                    handled_by = this.key
            this = this.parent

    def closing(self):
        return True

    def close(self):
        pass

def drawing(func):
    current_composition.get().drawings.append(func)
    return func

def post_drawing(func):
    current_composition.get().post_drawings.append(func)
    return func

def listen(event):
    return current_composition.get().listen(event, original=True)

def shape(shape):
    current_composition.get().shape = shape

def layout(layout):
    current_composition.get().layout = layout

def broadcast(e_event, *args):
    ui.get().custom_global_event(e_event, *args)

def inform(e_event, this, *args):
    ui.get().custom_event(e_event, this, *args)

class Hit:
    def trace(self, ctx):
        pass

    def test(self, x, y):
        return True

class Circle(Hit):
    def __init__(self, x, y, radius):
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
    def __init__(self, x, y, width, height):
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

    def __repr__(self):
        return f"Box({self.x}, {self.y}, {self.width}, {self.height})"

class Hidden(Hit):
    def trace(self, ctx):
        pass

    def test(self, x, y):
        return False

class StaticLayout:
    def measure(self, children, available_width, available_height):
        for child in children:
            child.layout.measure(child.children, available_width, available_height)

    def __call__(self, this, box, shallow=True):
        for child in this.children:
            if child.layout is not None:
                child.layout(child, this.shape)

class DynamicLayout:
    def __init__(self, width=0, height=0, flexible_width=False, flexible_height=False):
        self.width = width
        self.height = height
        self.flexible_width = flexible_width
        self.flexible_height = flexible_height

    def measure(self, children, available_width, available_height):
        if self.flexible_width:
            self.width = available_width
        if self.flexible_height:
            self.height = available_height
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(child.children, shape.width, shape.height)
            elif child.layout is not None:
                child.layout.measure(child.children, self.width, self.height)

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        for child in this.children:
            if child.layout is not None:
                child.layout(child, this.shape)
    
def align_low(pos, space, available_space):
    return pos

def align_middle(pos, space, available_space):
    return pos + available_space / 2 - space / 2

def align_high(pos, space, available_space):
    return pos + available_space - space

class RowLayout(DynamicLayout):
    def __init__(self, align = align_low):
        super().__init__(flexible_height = True)
        self.align = align

    def measure(self, children, available_width, available_height):
        total_width = 0
        max_height = 0
        flexibles = []
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(child.children, shape.width, shape.height)
                continue
            elif child.layout is None:
                continue
            if child.layout.flexible_width:
                flexibles.append(child)
            else:
                child.layout.measure(child.children, child.layout.width, available_height)
                total_width += child.layout.width
                max_height = max(max_height, child.layout.height)
        if flexibles:
            remaining_width = available_width - total_width
            flexible_width = remaining_width / len(flexibles)
            for child in flexibles:
                child.layout.measure(child.children, flexible_width, available_height)
                total_width += child.layout.width
                max_height = max(max_height, child.layout.height)
        self.width = total_width
        self.height = max_height

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        current_x = box.x
        for child in this.children:
            if child.layout is not None:
                width = child.layout.width
                height = child.layout.height
                current_y = self.align(box.y, height, box.height)
                shape = Box(current_x, current_y, width, height)
                child.layout(child, shape)
                current_x += width

class ColumnLayout(DynamicLayout):
    def __init__(self, align = align_low):
        super().__init__(flexible_width = True)
        self.align = align

    def measure(self, children, available_width, available_height):
        total_height = 0
        max_width = 0
        flexibles = []
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(child.children, shape.width, shape.height)
                continue
            elif child.layout is None:
                continue
            if child.layout.flexible_height:
                flexibles.append(child)
            else:
                child.layout.measure(child.children, available_width, child.layout.height) 
                total_height += child.layout.height
                max_width = max(max_width, child.layout.width)
        if flexibles:
            remaining_height = available_height - total_height
            flexible_height = remaining_height / len(flexibles)
            for child in flexibles:
                child.layout.measure(child.children, available_width, flexible_height)
                total_height += child.layout.height
                max_width = max(max_width, child.layout.width)
        self.width = max_width
        self.height = total_height

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        current_y = box.y
        for child in this.children:
            if child.layout is not None:
                width = child.layout.width
                height = child.layout.height
                current_x = self.align(box.x, width, box.width)
                shape = Box(current_x, current_y, width, height)
                child.layout(child, shape)
                current_y += height

class ScrollableLayout(DynamicLayout):
    def __init__(self, inner, state, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inner = inner
        self.scroll_x = state.scroll_x
        self.scroll_y = state.scroll_y
        self.scale_x = state.scale_x
        self.scale_y = state.scale_y

    def measure(self, children, available_width, available_height):
        if self.flexible_width:
            self.width = available_width
        if self.flexible_height:
            self.height = available_height
        self.inner.measure(children, self.width / self.scale_x, self.height / self.scale_y)

    def __call__(self, this, box, shallow=True):
        assert shallow
        max_scroll_x = max(0, self.inner.width - box.width/self.scale_x)
        max_scroll_y = max(0, self.inner.height - box.height/self.scale_y)

        # Adjust scroll positions to be within the valid range
        self.scroll_x = max(0, min(self.scroll_x, max_scroll_x))
        self.scroll_y = max(0, min(self.scroll_y, max_scroll_y))

        inner_box = Box(0, 0, self.inner.width, self.inner.height)
        matrix = cairo.Matrix()
        matrix.translate(box.x, box.y)
        matrix.scale(self.scale_x, self.scale_y)
        matrix.translate(-self.scroll_x, -self.scroll_y)
        this.transform = matrix
        this.shape = box
        self.inner(this, inner_box, shallow=False)

class PaddedLayout(DynamicLayout):
    def __init__(self, inner, top=0, right=0, bottom=0, left=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inner = inner
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left

    def measure(self, children, available_width, available_height):
        self.inner.measure(children,
            available_width - self.left - self.right,
            available_height - self.top - self.bottom)
        self.width = self.inner.width + self.left + self.right
        self.height = self.inner.height + self.top + self.bottom

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        inner_box = Box(
            box.x + self.left,
            box.y + self.top,
            self.inner.width,
            self.inner.height)
        self.inner(this, inner_box, shallow=False)

def sub(fn, d=0):
    comp = current_composition.get()
    key = comp.get_callsite_key(None, 2+d)
    previous = ui_memo.get().get(key)
    state = {} if previous is None else previous.state
    this = Composition(comp, key, None, state)
    comp.children.append(this)
    with composition_context(this, memoize(previous)):
        fn()
    return this

def column(align = align_low):
    def _decorator_(fn):
        this = sub(fn, 1)
        this.layout = ColumnLayout(align)
        return this
    return _decorator_

def row(align = align_low):
    def _decorator_(fn):
        this = sub(fn, 1)
        this.layout = RowLayout(align)
        return this
    return _decorator_

@composable
def hspacing(x):
    layout(DynamicLayout(width = x, flexible_height=True))

@composable
def vspacing(y):
    layout(DynamicLayout(height = y, flexible_width=True))

def workspace(color=(1,1,1,1), font_family=None):
    layout(DynamicLayout(flexible_width=True, flexible_height=True))
    if font_family is not None:
        ui.get().ctx.select_font_face(font_family)
    @drawing
    def _workspace_(ui, _):
        ctx = ui.ctx
        ctx.set_source_rgba(*color)
        ctx.rectangle(0, 0, ui.widget.width, ui.widget.height)
        ctx.fill()

