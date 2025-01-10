from kiwisolver import Variable, Solver
from reaction import *
from collections import namedtuple
import sdl2
import moderngl

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

def cover(left, bottom, width, height, x, y):
    return True

def circle(left, bottom, width, height, x, y):
    radius = min(width, height)/2
    dx = left + width/2 - x
    dy = bottom + height/2 - y
    return dx*dx + dy*dy <= radius*radius

def box(left, bottom, width, height, x, y):
    ix = left <= x < left + width
    iy = bottom <= y < bottom + height
    return ix and iy

def hidden(left, bottom, width, height, x, y):
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
        self.bottom  = Variable()
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
        return self.bottom + self.height/2

    @property
    def right(self):
        return self.left + self.width

    @property
    def top(self):
        return self.bottom + self.height

    @property
    def computed_box(self):
        left = self.left.value()
        bottom  = self.bottom.value()
        width = self.width.value()
        height = self.height.value()
        return left, bottom, width, height

    def hittest(self, x, y):
        left = self.left.value()
        bottom  = self.bottom.value()
        width = self.width.value()
        height = self.height.value()
        return self.shape(left, bottom, width, height, x, y)

    def constrain(self, ui, solver):
        for item in self.contents:
            if isinstance(item, Layout):
                item.constrain(ui, self, solver)
  
    def hit(self, x, y):
        if self.hittest(x, y):
            return self

    def draw(self, ui):
        for content in self.contents:
            if isinstance(content, Draw):
                content.func(ui, self, *map(sample, content.sources))
            elif isinstance(content, Frame):
                content.draw(ui)

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
        solver.addConstraint((this.bottom == (height - this.height) * self.ratio) | 'strong')

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
            solver.addConstraint(this.bottom <= frame.bottom)
            solver.addConstraint(frame.top <= this.top)
            bar = frame.right
        solver.addConstraint((bar == this.right) | 'medium')

class Draw(Detail):
    def __init__(self, func, sources):
        self.func = func
        self.sources = sources

    def attach(self, ui, frame):
        frame.observers.add(ui.engine.observe(*self.sources)(ui._refresh_))

def common_interface(ui):
    ui.ctx.includes['common_ui'] = """
        #define PI 3.1415926535897932384626433832795
        uniform vec2 size;
        vec2 pixel_to_screen(vec2 pixel) {
            return pixel / size * 2.0 - 1.0;
        }
    """

def plain_line_program(ui):
    ui.mem(common_interface)
    program = ui.ctx.program(
        vertex_shader="""
            #version 330
            #include "common_ui"
            in vec2 point;
            void main() {
                gl_Position = vec4(pixel_to_screen(point), 0.0, 1.0);
            }
        """,
        fragment_shader="""
            #version 330
            uniform vec4 color;
            out vec4 rgba;
            void main() {
                rgba = color;
            }
        """
    )
    return program

def circle_filler(ui):
    ui.mem(common_interface)
    program = ui.ctx.program(
        vertex_shader="""
            #version 330
            #include "common_ui"
            uniform vec4 rect;
            void main() {
                if (gl_VertexID == 0) {
                    gl_Position = vec4(pixel_to_screen(rect.zw*0.5 + rect.xy), 0.0, 1.0);
                } else {
                    float s = (gl_VertexID - 1) / 100.0;
                    vec2 p = vec2(cos(s*PI), sin(s*PI)) / 2 + 0.5;
                    vec2 r = p * rect.zw + rect.xy;
                    gl_Position = vec4(pixel_to_screen(r), 0.0, 1.0);
                }
            }
        """,
        fragment_shader="""
            #version 330
            uniform vec4 color;
            out vec4 rgba;
            void main() {
                rgba = color;
            }
        """
    )
    vao = ui.ctx.vertex_array(program, [])
    return vao, program

def _circle_filler_(ui, this, color):
    vao, program = ui.mem(circle_filler)
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = this.computed_box
    program['color'] = color
    vao.render(vertices=202, mode=ui.ctx.TRIANGLE_FAN)

def circle_fill(color):
    return Draw(_circle_filler_, [color])

def circle_stroker(ui):
    ui.mem(common_interface)
    program = ui.ctx.program(
        vertex_shader="""
            #version 330
            #include "common_ui"
            uniform vec4 rect;
            void main() {
                int k = (gl_VertexID+1)/2;
                float s = k / 100.0;
                vec2 p = vec2(cos(s*PI), sin(s*PI)) / 2 + 0.5;
                vec2 r = p * rect.zw + rect.xy;
                gl_Position = vec4(pixel_to_screen(r), 0.0, 1.0);
            }
        """,
        fragment_shader="""
            #version 330
            uniform vec4 color;
            out vec4 rgba;
            void main() {
                rgba = color;
            }
        """
    )
    vao = ui.ctx.vertex_array(program, [])
    return vao, program

def _circle_stroke_(ui, this, color):
    vao, program = ui.mem(circle_stroker)
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = this.computed_box
    program['color'] = color
    vao.render(vertices=200*2, mode=ui.ctx.LINES)

def circle_stroke(color):
    return Draw(_circle_stroke_, [color])

def rectangle_filler(ui):
    ui.mem(common_interface)
    program = ui.ctx.program(
        vertex_shader="""
            #version 330
            #include "common_ui"
            uniform vec4 rect;
            vec2 square[4] = vec2[](
                vec2(1,0), vec2(0,0), vec2(1,1), vec2(0,1)
            );
            void main() {
                vec2 r = square[gl_VertexID] * rect.zw + rect.xy;
                gl_Position = vec4(pixel_to_screen(r), 0.0, 1.0);
            }
        """,
        fragment_shader="""
            #version 330
            uniform vec4 color;
            out vec4 rgba;
            void main() {
                rgba = color;
            }
        """
    )
    vao = ui.ctx.vertex_array(program, [])
    return vao, program

def rectangle_stroker(ui):
    ui.mem(common_interface)
    program = ui.ctx.program(
        vertex_shader="""
            #version 330
            #include "common_ui"
            uniform vec4 rect;
            vec2 square[8] = vec2[](
                vec2(0,0), vec2(1,0), vec2(1,0), vec2(1,1),
                vec2(1,1), vec2(0,1), vec2(0,1), vec2(0,0)
            );
            void main() {
                vec2 r = square[gl_VertexID] * rect.zw + rect.xy;
                gl_Position = vec4(pixel_to_screen(r), 0.0, 1.0);
            }
        """,
        fragment_shader="""
            #version 330
            uniform vec4 color;
            out vec4 rgba;
            void main() {
                rgba = color;
            }
        """
    )
    vao = ui.ctx.vertex_array(program, [])
    return vao, program

def _trace_draw_(ui, this, color):
    vao, program = ui.mem(rectangle_stroker)
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = this.computed_box
    program['color'] = color
    vao.render(vertices=8, mode=ui.ctx.LINES)
    
def trace(color):
    return Draw(_trace_draw_, [color])

def _fill_draw_(ui, this, color):
    vao, program = ui.mem(rectangle_filler)
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = this.computed_box
    program['color'] = color
    vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)

def fill(color):
    return Draw(_fill_draw_, [color])
 
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
        self.renderer = sdl2.SDL_GL_CreateContext(widget.window.window)
        self.ctx = moderngl.create_context()
        self.memo = dict()
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

    def mem(self, *args):
        if args not in self.memo:
            self.memo[args] = args[0](self, *args[1:])
        return self.memo[args]

    def reconstrain(self):
        self.solver.reset()
        self.root.constrain(self, self.solver)
        self.solver.addEditVariable(self.root.left, 'strong')
        self.solver.addEditVariable(self.root.bottom, 'strong')
        self.solver.addEditVariable(self.root.width, 'weak')
        self.solver.addEditVariable(self.root.height, 'weak')
        self.solver.suggestValue(self.root.left, 0)
        self.solver.suggestValue(self.root.bottom, 0)
        self._refresh_()

    def _refresh_(self, *_):
        self.resized()

    def resized(self):
        self.widget.exposed = True
        self.solver.suggestValue(self.root.width, self.widget.width)
        self.solver.suggestValue(self.root.height, self.widget.height)
        self.solver.updateVariables()

    def draw(self):
        self.ctx.viewport = 0,0,self.widget.width,self.widget.height
        self.ctx.clear(1,1,1,1)
        self.root.draw(self)
        sdl2.SDL_GL_SwapWindow(self.widget.window.window)

    def update(self):
        self.engine.send(self.pulse, sdl2.SDL_GetTicks64() / 1000.0)
        self.engine.roll()

    def mouse_motion(self, x, y):
        y = self.widget.height - y
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
        y = self.widget.height - y
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
        y = self.widget.height - y
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
        sdl2.SDL_GL_DeleteContext(self.renderer)
