from kiwisolver import Variable, Solver
from reaction import *
from collections import namedtuple
from . import cairo_renderer
import cairo
import sdl2

class ButtonControl:
    def __init__(self, ui):
        self.up = Source(ui.engine)
        self.down = Source(ui.engine)
        self.pressed = Source(ui.engine)

class MouseControl:
    def __init__(self, ui):
        self.inside = Source(ui.engine)
        self.enter  = Source(ui.engine)
        self.leave  = Source(ui.engine)
        self.left   = ButtonControl(ui)
        self.middle = ButtonControl(ui)
        self.right  = ButtonControl(ui)
        self.motion = Source(ui.engine)

    def by_button_id(self, button):
        if button == 1:
            return self.left
        elif button == 2:
            return self.middle
        elif button == 3:
            return self.right

class KeyboardControl:
    def __init__(self, ui):
        self.focus = Source(ui.engine)
        self.enter = Source(ui.engine)
        self.leave = Source(ui.engine)
        self.stream = Source(ui.engine, as_stream)

Down = namedtuple('Down', ['sym', 'repeat', 'modifiers'])
Up   = namedtuple('Up', ['sym', 'modifiers'])
Text = namedtuple('Text', ['text'])

def cover(left, top, width, height, x, y):
    return True

def circle(left, top, width, height, x, y):
    radius = min(width, height)/2
    dx = left + width/2 - x
    dy = top + height/2 - y
    return dx*dx + dy*dy <= radius*radius

def box(left, top, width, height, x, y):
    ix = left <= x < left + width
    iy = top <= y < top + height
    return ix and iy

def hidden(left, top, width, height, x, y):
    return False

class Detail:
    def attach(self, ui, parent):
        pass

    def detach(self):
        pass

class Frame(Detail):
    def __init__(self, contents, shape=box, mouse=None, keyboard=None):
        self.parent = None
        self.contents = contents
        self.left = Variable()
        self.top  = Variable()
        self.width  = Variable()
        self.height = Variable()
        self.shape = shape
        self.mouse = mouse
        self.keyboard = keyboard
        self.observers = set()

    @property
    def hcenter(self):
        return self.left + self.width/2

    @property
    def vcenter(self):
        return self.top + self.height/2

    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def computed_box(self):
        left = self.left.value()
        top  = self.top.value()
        width = self.width.value()
        height = self.height.value()
        return left, top, width, height

    def hittest(self, x, y):
        left = self.left.value()
        top  = self.top.value()
        width = self.width.value()
        height = self.height.value()
        return self.shape(left, top, width, height, x, y)

    def constrain(self, ui, solver):
        for item in self.contents:
            if isinstance(item, Layout):
                item.constrain(ui, self, solver)
  
    def hit(self, x, y):
        if self.hittest(x, y):
            return self

    def draw(self, ui):
        for content in self.contents:
            ui.ctx.save()
            try:
                if isinstance(content, Draw):
                    content.func(ui, self, *map(sample, content.sources))
                elif isinstance(content, Frame):
                    content.draw(ui)
            finally:
                ui.ctx.restore()

    def attach(self, ui, parent):
        self.parent = parent
        for content in self.contents:
            content.attach(ui, self)

    def detach(self):
        self.parent = None
        for obs in self.observers:
            obs.discard()
        self.observers.clear()
        for content in self.contents:
            content.detach()

class Container(Frame):
    @property
    def subframes(self):
        return [item for item in self.contents if isinstance(item, Frame)]

    def hit(self, x, y):
        if self.hittest(x, y):
            selection = self
            for content in self.subframes:
                selection = content.hit(x, y) or selection
            return selection

    def constrain(self, ui, solver):
        for item in self.contents:
            if isinstance(item, Layout):
                item.constrain(ui, self, solver)
            if isinstance(item, Frame):
                item.constrain(ui, solver)
            
class Layout(Detail):
    def __init__(self, *sources):
        self.sources = sources

    def refresh(self, ui, frame, *xs):
        ui._refresh_(*xs)

    def attach(self, ui, frame):
        if len(self.sources) > 0:
            _refresh_ = lambda *xs: self.refresh(ui, frame, *xs)
            frame.observers.add(ui.engine.observe(*self.sources)(_refresh_))

class CustomLayout(Layout):
    def __init__(self, func0, func1, *sources):
        super().__init__(*sources)
        self.func0 = func0
        self.func1 = func1

    def refresh(self, ui, frame, *xs):
        self.func1(ui, frame, ui.solver, *xs)
        super().refresh(ui, frame, *xs)

    def constrain(self, ui, this, solver):
        self.func0(ui, this, solver, *map(sample, self.sources))
        self.func1(ui, this, solver, *map(sample, self.sources))

class HAlign(Layout):
    def __init__(self, ratio):
        super().__init__()
        self.ratio = ratio

    def constrain(self, ui, this, solver):
        width = this.parent.width
        solver.addConstraint((this.left == (width - this.width) * self.ratio) | 'strong')

class VAlign(Layout):
    def __init__(self, ratio):
        super().__init__()
        self.ratio = ratio

    def constrain(self, ui, this, solver):
        height = this.parent.height
        solver.addConstraint((this.top == (height - this.height) * self.ratio) | 'strong')

class Width(Layout):
    def __init__(self, value):
        super().__init__(value)

    def constrain(self, ui, this, solver):
        solver.addEditVariable(this.width, 'strong')
        solver.suggestValue(this.width, sample(self.sources[0]))

    def refresh(self, ui, this, value):
        ui.solver.suggestValue(this.width, value)
        super().refresh(ui, this, value)

class Height(Layout):
    def __init__(self, value):
        super().__init__(value)

    def constrain(self, ui, this, solver):
        solver.addEditVariable(this.height, 'strong')
        solver.suggestValue(this.height, sample(self.sources[0]))

    def refresh(self, ui, this, value):
        ui.solver.suggestValue(this.height, value)
        super().refresh(ui, this, value)

class Column(Layout):
    def constrain(self, ui, this, solver):
        bar = this.top
        for frame in this.subframes:
            solver.addConstraint(bar == frame.top)
            solver.addConstraint(this.left <= frame.left)
            solver.addConstraint(frame.right <= this.right)
            bar = frame.bottom
        solver.addConstraint((bar == this.bottom) | 'medium')

class Row(Layout):
    def constrain(self, ui, this, solver):
        bar = this.left
        for frame in this.subframes:
            solver.addConstraint(bar == frame.left)
            solver.addConstraint(this.top <= frame.top)
            solver.addConstraint(frame.bottom <= this.bottom)
            bar = frame.right
        solver.addConstraint((bar == this.right) | 'medium')

class Draw(Detail):
    def __init__(self, func, sources):
        self.func = func
        self.sources = sources

    def attach(self, ui, frame):
        frame.observers.add(ui.engine.observe(*self.sources)(ui._refresh_))

def _trace_draw_(ui, this, color):
    ui.ctx.set_source_rgba(*color)
    ui.ctx.rectangle(*this.computed_box)
    ui.ctx.stroke()
def trace(color):
    return Draw(_trace_draw_, [color])
 
def drawing(*sources):
    def _decorator_(func):
        return Draw(func, sources)
    return _decorator_

class Logic(Detail):
    def __init__(self, func, sources):
        self.func = func
        self.sources = sources

    def attach(self, ui, frame):
        self.func(ui, frame, *map(sample, self.sources))
        wrapper = lambda *xs: self.func(ui, frame, *xs)
        frame.observers.add(ui.engine.observe(*self.sources)(wrapper))

def logic(*sources):
    def _decorator_(func):
        return Logic(func, sources)
    return _decorator_
 
class GUI:
    def __init__(self, widget, scene, *args, **kwargs):
        self.widget = widget
        self.renderer = cairo_renderer.Renderer(widget)
        self.ctx = cairo.Context(self.renderer.surface)
        self.engine = Engine()
        self.mouse_position = Event()
        self.pulse = Event()
        self.now = Hold(sdl2.SDL_GetTicks64() / 1000.0, self.pulse)

        self.solver = Solver()
        self.root = scene(self, *args, **kwargs)
        self.root.attach(self, None)
        self.reconstrain()

        self.mouse = MouseControl(self)
        self.keyboard = KeyboardControl(self)

        self.keyboard_focus = None
        self.button_presses = dict()
        self.under_motion = None

    def reconstrain(self):
        self.solver.reset()
        self.root.constrain(self, self.solver)
        self.solver.addEditVariable(self.root.left, 'strong')
        self.solver.addEditVariable(self.root.top, 'strong')
        self.solver.addEditVariable(self.root.width, 'weak')
        self.solver.addEditVariable(self.root.height, 'weak')
        self.solver.suggestValue(self.root.left, 0)
        self.solver.suggestValue(self.root.top, 0)
        self._refresh_()

    def _refresh_(self, *_):
        self.widget.exposed = True
        self.solver.suggestValue(self.root.width, self.widget.width)
        self.solver.suggestValue(self.root.height, self.widget.height)
        self.solver.updateVariables()

    def draw(self):
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
        self.mouse.motion.send((x,y))
        this = self.root.hit(x, y)
        handled_by = None
        if len(self.button_presses) > 0 and self.under_motion is not None:
            that = self.under_motion
            that.mouse.motion.send((x,y))
            return
        while this is not None and handled_by is None:
            if this.mouse:
                handled_by = this
            this = this.parent
        if handled_by != self.under_motion:
            that = self.under_motion
            if handled_by:
                handled_by.mouse.inside.send(True)
                handled_by.mouse.enter.send(None)
            if that:
                that.mouse.inside.send(False)
                that.mouse.leave.send(None)
        self.under_motion = handled_by
        if handled_by:
            handled_by.mouse.motion.send((x,y))

    def mouse_button_down(self, x, y, button):
        self.mouse.motion.send((x,y))
        ctl = self.mouse.by_button_id(button)
        if ctl:
            ctl.down.send(None)
            ctl.pressed.send(True)
        this = self.root.hit(x, y)
        handled_by = None
        focus_by = None
        while this is not None and (handled_by is None or focus_by is None):
            if this.mouse and (handled_by is None):
                handled_by = this
            if this.keyboard and (focus_by is None):
                focus_by = this
            this = this.parent
        if handled_by is not None:
            self.button_presses[button] = handled_by
            ctl = handled_by.mouse.by_button_id(button)
            if ctl:
                ctl.down.send(None)
                ctl.pressed.send(True)
        if focus_by is not None:
            if self.keyboard_focus:
                self.keyboard_focus.keyboard.leave.send(None)
                self.keyboard_focus.keyboard.focus.send(False)
            self.keyboard_focus = focus_by
            focus_by.keyboard.enter.send(None)
            focus_by.keyboard.focus.send(True)
 
    def mouse_button_up(self, x, y, button):
        self.mouse.motion.send((x,y))
        ctl = self.mouse.by_button_id(button)
        if ctl:
            ctl.up.send(None)
            ctl.pressed.send(False)
        this = self.button_presses.pop(button, None)
        if this:
            ctl = this.mouse.by_button_id(button)
            if ctl:
                ctl.up.send(None)
                ctl.pressed.send(False)
 
    def text_input(self, text):
        action = Text(text)
        self.keyboard.stream.send(action)
        this = self.keyboard_focus
        if this:
            this.keyboard.stream.send(action)

    def key_down(self, sym, repeat, modifiers):
        action = Down(sym, repeat, modifiers)
        self.keyboard.stream.send(action)
        this = self.keyboard_focus
        if this:
            this.keyboard.stream.send(action)

    def key_up(self, sym, modifiers):
        action = Up(sym, modifiers)
        self.keyboard.stream.send(action)
        this = self.keyboard_focus
        if this:
            this.keyboard.stream.send(action)

    def closing(self):
        return True

    def close(self):
        pass
