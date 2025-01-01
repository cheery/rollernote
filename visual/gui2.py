import math
import inspect
import cairo
import sdl2
from . import cairo_renderer
from contextlib import contextmanager
from contextvars import ContextVar
from reaction import *
from collections import namedtuple

Down = namedtuple('Down', ['sym', 'repeat', 'modifiers'])
Up   = namedtuple('Up', ['sym', 'modifiers'])

identity_transform = cairo.Matrix()

class Varying:
    def __init__(self, cell):
        self.cell = cell
        self.value = None

    def wrap(self, ui, this):
        def _func_(new_value):
            self.value.detach()
            new_value.attach(ui, this)
            self.value = new_value
        return _func_

class Frame:
    def __init__(self, contents, layout=None, shape=None, inside=None, keyboard=None, chars=None, motion=None, buttons=None):
        self.parent = None
        self.contents = contents
        self.layout = layout or DynamicLayout(flexible_width=True, flexible_height=True)
        self.transform = identity_transform
        self.clipping = False
        self.shape = shape or hit
        self.buttons  = buttons
        self.inside   = inside
        self.keyboard = keyboard
        self.chars    = chars
        self.motion   = motion
        self.subscriptions = []

    def attach(self, ui, parent):
        self.parent = parent
        for content in self.contents:
            if isinstance(content, Logic):
                def initial_of(flow):
                    if isinstance(flow, Cell):
                        return flow.value
                    return []
                content.func(ui, self, *map(initial_of, content.sources))
                self.subscriptions.append(
                    ui.engine.observe(*content.sources)(content.wrap(ui, self)))
            elif isinstance(content, Draw):
                self.subscriptions.append(
                    ui.engine.observe(*content.sources)(ui._refresh_))
            elif isinstance(content, Varying):
                content.value = content.cell.value
                content.value.attach(ui, self)
                self.subscriptions.append(
                    ui.engine.observe(content.cell)(content.wrap(ui, self)))
            else:
                content.attach(ui, self)

    def detach(self):
        self.parent = None
        for obs in self.subscriptions:
            obs.discard()
        self.subscriptions = []
        for content in self.subframes():
            content.detach()

    def draw(self, ui):
        for content in self.contents:
            ui.ctx.save()
            try:
                if isinstance(content, Varying):
                    content = content.value
                if isinstance(content, Draw):
                    if content.in_clip:
                        self.shape.trace(ui.ctx)
                        ui.ctx.clip()
                    if content.in_transform:
                        ui.ctx.transform(self.transform)
                    content.func(ui, self, *(s.value for s in content.sources))
                elif isinstance(content, Frame):
                    if self.clipping:
                        self.shape.trace(ui.ctx)
                        ui.ctx.clip()
                    ui.ctx.transform(self.transform)
                    content.draw(ui)
            finally:
                ui.ctx.restore()

    def local_point(self, x, y):
        matrix = self.transform
        this = self.parent
        while this is not None:
            matrix = this.transform * matrix
            this = this.parent
        matrix.invert()
        return matrix.transform_point(x, y)
 
    def hit(self, x, y):
        if self.shape.test(x, y):
            matrix = cairo.Matrix(*self.transform)
            matrix.invert()
            x, y = matrix.transform_point(x, y)
            selection = self
            for content in self.subframes():
                selection = content.hit(x, y) or selection
            return selection

    def subframes(self):
        for content in self.contents:
            if isinstance(content, Frame):
                yield content
            elif isinstance(content, Varying):
                yield content.value

    def preorder(self):
        yield self
        for content in self.subframes():
            yield from contents.preorder()

class Draw:
    def __init__(self, in_clip, in_transform, func, sources):
        self.in_clip = in_clip
        self.in_transform = in_transform
        self.func = func
        self.sources = sources

def _trace_draw_(ui, this):
    #rgba = this.properties.get('trace_color', None)
    #if rgba is not None:
    #    ui.ctx.set_source_rgba(*rgba.value)
    #else:
    ui.ctx.set_source_rgba(0.0,0.0,0.0,1.0)
    this.shape.trace(ui.ctx)
    ui.ctx.stroke()
trace = Draw(False, False, _trace_draw_, [])

def drawing(*sources, in_clip=False, in_transform=False):
    def _decorator_(func):
        return Draw(in_clip, in_transform, func, sources)
    return _decorator_

class Logic:
    def __init__(self, sources, func):
        self.sources = sources
        self.func = func

    def wrap(self, ui, this):
        return lambda *xs: self.func(ui, this, *xs)

def logic(*sources):
    def _decorator_(func):
        return Logic(sources, func)
    return _decorator_

def column(contents, **properties):
    return Frame(contents, ColumnLayout(), **properties)

def row(contents, **properties):
    return Frame(contents, RowLayout(), **properties)

def hspacing(x):
    return Frame([], DynamicLayout(width=x, flexible_height=True))

def vspacing(x):
    return Frame([], DynamicLayout(height=x, flexible_width=True))

class GUI:
    def __init__(self, widget, scene, *args, **kwargs):
        self.widget = widget
        self.renderer = cairo_renderer.Renderer(widget)
        self.ctx = cairo.Context(self.renderer.surface)
        self.engine = Engine()
        self.mouse_position = Event()
        self.pulse = Event()
        self.now = Hold(sdl2.SDL_GetTicks64() / 1000.0, self.pulse)
        self.mouse_button_left   = Event()
        self.mouse_button_middle = Event()
        self.mouse_button_right  = Event()
        self.chars = Event()
        self.keyboard = Event()

        self.keyboard_focus = None
        self.button_presses = dict()
        self.under_motion = None

        self.root = scene(self, *args, **kwargs)
        self.root.attach(self, None)

    def _refresh_(self, *_):
        self.widget.exposed = True

    def draw(self):
        self.root.layout.measure(list(self.root.subframes()), self.widget.width, self.widget.height)
        if isinstance(self.root.layout, StaticLayout):
            self.root.layout(self.root, self.root.shape)
        elif self.root.layout is not None:
            shape = Box(0, 0, self.root.layout.calc_width, self.root.layout.calc_height)
            self.root.layout(self.root, shape)

        ctx = self.ctx

        ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        ctx.rectangle(0, 0, self.widget.width, self.widget.height)
        ctx.fill()

        self.root.draw(self)

        self.renderer.flip()

    def update(self):
        self.engine.send(self.pulse, sdl2.SDL_GetTicks64() / 1000.0)
        self.engine.roll()

    def mouse_motion(self, x, y):
        self.engine.send(self.mouse_position, (x,y))
        this = self.root.hit(x, y)
        handled_by = None
        if len(self.button_presses) > 0 and self.under_motion is not None:
            that = self.under_motion
            self.engine.send(that.motion, (x,y))
            return
        while this is not None and handled_by is None:
            if this.inside or this.motion:
                handled_by = this
            this = this.parent
        if handled_by != self.under_motion:
            that = self.under_motion
            if handled_by and handled_by.inside:
                self.engine.send(handled_by.inside, True)
            if self.under_motion and self.under_motion.inside:
                self.engine.send(self.under_motion.inside, False)
        self.under_motion = handled_by
        if handled_by and handled_by.motion:
            self.engine.send(handled_by.motion, (x,y))

    def mouse_button_down(self, x, y, button):
        self.engine.send(self.mouse_position, (x,y))
        btn = [self.mouse_button_left,
               self.mouse_button_middle,
               self.mouse_button_right][button-1]
        self.engine.send(btn, True)
        this = self.root.hit(x, y)
        handled_by = None
        focus_by = None
        while this is not None and (handled_by is None or focus_by is None):
            if this.buttons and (handled_by is None):
                handled_by = this
            if (this.keyboard or this.chars) and (focus_by is None):
                focus_by = this
            this = this.parent
        if handled_by is not None:
            self.button_presses[button] = handled_by
            self.engine.send(handled_by.buttons[button-1], True)
        if focus_by is not None:
            self.keyboard_focus = focus_by

    def mouse_button_up(self, x, y, button):
        self.engine.send(self.mouse_position, (x,y))
        btn = [self.mouse_button_left,
               self.mouse_button_middle,
               self.mouse_button_right][button-1]
        self.engine.send(btn, False)
        this = self.button_presses.pop(button, None)
        if this:
            self.engine.send(this.buttons[button-1], False)

    def text_input(self, text):
        for c in text:
            self.engine.send(self.chars, c)
        this = self.keyboard_focus
        if this and this.chars:
            self.engine.send(this.chars, c)

    def key_down(self, sym, repeat, modifiers):
        action = Down(sym, repeat, modifiers)
        self.engine.send(self.keyboard, action)
        this = self.keyboard_focus
        if this and this.keyboard:
            self.engine.send(this.keyboard, action)

    def key_up(self, sym, modifiers):
        action = Up(sym, modifiers)
        self.engine.send(self.keyboard, action)
        this = self.keyboard_focus
        if this and this.keyboard:
            self.engine.send(this.keyboard, action)

    def closing(self):
        return True

    def close(self):
        pass

class StaticLayout:
    def __init__(self, inner):
        self.inner = inner

    def measure(self, children, available_width, available_height):
        self.inner.measure(children, available_width, available_height)

    def __call__(self, this, box, shallow=True):
        self.inner(this, box)

class DynamicLayout:
    def __init__(self, width=0, height=0, flexible_width=False, flexible_height=False):
        self.width = width
        self.height = height
        self.flexible_width = flexible_width
        self.flexible_height = flexible_height
        self.calc_width = width
        self.calc_height = height

    def measure(self, children, available_width, available_height):
        if self.flexible_width:
            self.calc_width = max(self.width, available_width)
        if self.flexible_height:
            self.calc_height = max(self.height, available_height)
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(list(child.subframes()), shape.width, shape.height)
            elif child.layout is not None:
                child.layout.measure(list(child.subframes()), self.calc_width, self.calc_height)

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        for child in this.subframes():
            if isinstance(child.layout, StaticLayout):
                child.layout(child, child.shape)
            elif child.layout is not None:
                child.layout(child, box)
    
def align_low(pos, space, available_space):
    return pos

def align_middle(pos, space, available_space):
    return pos + available_space / 2 - space / 2

def align_high(pos, space, available_space):
    return pos + available_space - space

class RowLayout(DynamicLayout):
    def __init__(self, align = align_low, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.align = align

    def measure(self, children, available_width, available_height):
        if not self.flexible_width:
            available_width = self.width
        if not self.flexible_height:
            available_height = self.height
        total_width = 0
        max_height = 0
        flexibles = []
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(list(child.subframes()), shape.width, shape.height)
                continue
            elif child.layout is None:
                continue
            if child.layout.flexible_width and self.flexible_width:
                flexibles.append(child)
            else:
                child.layout.measure(list(child.subframes()), child.layout.width, available_height)
                total_width += child.layout.calc_width
                max_height = max(max_height, child.layout.calc_height)
        if flexibles:
            remaining_width = available_width - total_width
            flexible_width = remaining_width / len(flexibles)
            for child in flexibles:
                child.layout.measure(list(child.subframes()), flexible_width, available_height)
                total_width += child.layout.calc_width
                max_height = max(max_height, child.layout.calc_height)
        self.calc_width = max(self.width, total_width)
        self.calc_height = max(self.height, max_height)

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        current_x = box.x
        for child in this.subframes():
            if isinstance(child.layout, StaticLayout):
                child.layout(child, child.shape)
            elif child.layout is not None:
                width = child.layout.calc_width
                height = child.layout.calc_height
                current_y = self.align(box.y, height, box.height)
                shape = Box(current_x, current_y, width, height)
                child.layout(child, shape)
                current_x += width

class ColumnLayout(DynamicLayout):
    def __init__(self, align = align_low, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.align = align

    def measure(self, children, available_width, available_height):
        if not self.flexible_width:
            available_width = self.width
        if not self.flexible_height:
            available_height = self.height
        total_height = 0
        max_width = 0
        flexibles = []
        for child in children:
            if isinstance(child.layout, StaticLayout):
                shape = child.shape
                child.layout.measure(list(child.subframes()), shape.width, shape.height)
                continue
            elif child.layout is None:
                continue
            if child.layout.flexible_height and self.flexible_height:
                flexibles.append(child)
            else:
                child.layout.measure(list(child.subframes()), available_width, child.layout.height) 
                total_height += child.layout.calc_height
                max_width = max(max_width, child.layout.calc_width)
        if flexibles:
            remaining_height = available_height - total_height
            flexible_height = remaining_height / len(flexibles)
            for child in flexibles:
                child.layout.measure(list(child.subframes()), available_width, flexible_height)
                total_height += child.layout.calc_height
                max_width = max(max_width, child.layout.calc_width)
        self.calc_width = max(self.width, max_width)
        self.calc_height = max(self.height, total_height)

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        current_y = box.y
        for child in this.subframes():
            if isinstance(child.layout, StaticLayout):
                child.layout(child, child.shape)
            elif child.layout is not None:
                width = child.layout.calc_width
                height = child.layout.calc_height
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
            self.calc_width = available_width
        else:
            self.calc_width = self.width
        if self.flexible_height:
            self.calc_height = available_height
        else:
            self.calc_height = self.height
        self.inner.measure(children,
            self.calc_width / self.scale_x,
            self.calc_height / self.scale_y)

    def max_scroll(self):
        max_scroll_x = max(0, self.inner.calc_width - self.calc_width/self.scale_x)
        max_scroll_y = max(0, self.inner.calc_height - self.calc_height/self.scale_y)
        return max_scroll_x, max_scroll_y

    def clamp_scroll(self, scroll_x, scroll_y):
        max_scroll_x, max_scroll_y = self.max_scroll()

        # Adjust scroll positions to be within the valid range
        scroll_x = max(0, min(scroll_x, max_scroll_x))
        scroll_y = max(0, min(scroll_y, max_scroll_y))
        return scroll_x, scroll_y

    def __call__(self, this, box, shallow=True):
        assert shallow
        matrix = cairo.Matrix()
        matrix.translate(box.x, box.y)
        matrix.scale(self.scale_x, self.scale_y)
        matrix.translate(-self.scroll_x, -self.scroll_y)
        this.transform = matrix
        this.shape = box
        inner_box = Box(0, 0, self.inner.calc_width, self.inner.calc_height)
        self.inner(this, inner_box, shallow=False)

class PaddedLayout(DynamicLayout):
    def __init__(self, inner, top=0, right=0, bottom=0, left=0):
        super().__init__(inner.width + left + right,
                         inner.height + bottom + top,
                         inner.flexible_width,
                         inner.flexible_height)
        self.inner = inner
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left

    def measure(self, children, available_width, available_height):
        if not self.flexible_width:
            available_width = self.width + self.left + self.right
        if not self.flexible_height:
            available_height = self.height + self.top + self.bottom
        self.inner.measure(children,
            available_width - self.left - self.right,
            available_height - self.top - self.bottom)
        self.calc_width = self.inner.calc_width + self.left + self.right
        self.calc_height = self.inner.calc_height + self.top + self.bottom

    def __call__(self, this, box, shallow=True):
        if shallow:
            this.shape = box
        inner_box = Box(
            box.x + self.left,
            box.y + self.top,
            self.inner.calc_width,
            self.inner.calc_height)
        self.inner(this, inner_box, shallow=False)

class Hit:
    def trace(self, ctx):
        pass

    def test(self, x, y):
        return True

    def __repr__(self):
        return 'hit'
hit = Hit()

class Circle(Hit):
    def __init__(self, x, y, radius):
        self.x = x
        self.y = y
        self.radius = radius

    def trace(self, ctx):
        ctx.arc(self.x, self.y, self.radius, 0, 2*math.pi)

    def test(self, x, y):
        dx = self.x - x
        dy = self.y - y
        return dx*dx + dy*dy <= self.radius*self.radius

    def __repr__(self):
        return f"Circle({self.x}, {self.y}, {self.radius})"

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

    def __repr__(self):
        return 'hidden'
hidden = Hidden()
