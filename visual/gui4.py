from kiwisolver import Variable, Solver
from reaction import *
from collections import namedtuple
from contextvars import ContextVar
import sdl2
import moderngl
import typing

context = ContextVar('context')

def snap_all(args, kwargs):
    return [snap(x) for x in args], {k:snap(v) for k,v in kwargs.items()}

def check_all(args, kwargs, tests):
    test, kwtest = tests
    k = len(set(kwtest).union(kwargs))
    if len(test) != len(args) or not len(kwtest) == len(kwargs) == k:
        return False
    else:
        a = all(t(x) for t,x in zip(test, args))
        b = all(t(x) for _,t,x in common_entries(kwtest, kwargs))
        return a and b

def snap(x):
    if is_small(x):
        return small_test(x)
    elif hasattr(x, 'version'):
        return version_test(x, x.version)
    elif isinstance(x, Reusable):
        return ident_test(x)
    else:
        return no_test

def is_small(x):
    if isinstance(x, tuple):
        return all(map(is_small, x))
    return x is None or isinstance(x, (int,bool,float,str))

def small_test(x):
    return lambda y: x == y

def version_test(x, version):
    return lambda y: x is y and x.version == version

def ident_test(x):
    return lambda y: x is y

def no_test(y):
    return False

def common_entries(d1, d2):
    for i in set(d1).intersection(d2):
        yield (i,d1[i],d2[i])

class resource:
    def __init__(self, func):
        self.func = func

    def __getitem__(self, key):
        return keyed_resource(self, key)

    def invoke(self, key, args, kwargs):
        parent, memo = context.get()
        try:
            memo[key].reuse(parent)
            return memo[key]
        except KeyError:
            return self.func(key, parent, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.invoke(self, args, kwargs)

class keyed_resource:
    def __init__(self, res, key):
        self.res = res
        self.key = key

    def __call__(self, *args, **kwargs):
        return self.res.invoke((self.res, self.key), args, kwargs)

class composable:
    def __init__(self, func):
        self.func = func

    def __getitem__(self, key):
        return keyed_composable(self, key)

    def invoke(self, key, args, kwargs):
        parent, memo = context.get()
        renew = False
        try:
            component = memo[key]
            if check_all(args, kwargs, component.test):
                component.reuse(parent)
            else:
                renew = True
                memo = component.explode()
        except KeyError:
            renew = True
            memo = dict()
        if renew:
            test = snap_all(args, kwargs)
            component = Container(key, parent, test)
            token = context.set((component, memo))
            try:
                self.func(*args, **kwargs)
            finally:
                context.reset(token)
        return component

    def __call__(self, *args, **kwargs):
        return self.invoke(self, args, kwargs)

class keyed_composable:
    def __init__(self, com, key):
        self.com = com
        self.key = key

    def __call__(self, *args, **kwargs):
        return self.com.invoke((self.com, self.key), args, kwargs)

class Detail:
    pass

class Reusable(Detail):
    def __init__(self, key, parent):
        self.key = key
        self.parent = parent
        if parent is not None:
            parent.contents.append(self)

    def reuse(self, parent):
        self.parent = parent
        parent.contents.append(self)

def cover(xy, rect):
    return True

def circle(xy, rect):
    x, y = xy
    left, bottom, width, height = rect
    radius = min(width, height)/2
    dx = left + width/2 - x
    dy = bottom + height/2 - y
    return dx*dx + dy*dy <= radius*radius

def box(xy, rect):
    x, y = xy
    left, bottom, width, height = rect
    ix = left <= x < left + width
    iy = bottom <= y < bottom + height
    return ix and iy

def hidden(xy, rect):
    return False

class Frame(Reusable):
    def __init__(self, key, parent):
        super().__init__(key, parent)
        self.contents = []
        self.static = None
        self.shape = box
        self.logic_func = None

    @property
    def subframes(self):
        return [item for item in self.contents if isinstance(item, Frame)]

class Container(Frame):
    def __init__(self, key, parent, test):
        super().__init__(key, parent)
        self.test = test

    def explode(self):
        memo = dict()
        for content in self.contents:
            if isinstance(content, Reusable):
                memo[content.key] = content
        return memo

class State(Reusable):
    def __init__(self, key, parent, data):
        super().__init__(key, parent)
        self.data = data
        self.version = 0

    def __getattr__(self, name):
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError

    def __setattr__(self, name, value):
        try:
            super().__setattr__(name, value)
        except AttributeError:
            if name in self.data:
                self.data[name] = value
                self.version += 1
            else:
                raise AttributeError

@resource
def state(key, parent, **data):
    return State(key, parent, data)

class Draw(Detail):
    def __init__(self, func):
        self.func = func

def drawing(func):
    parent = context.get()[0]
    parent.contents.append(Draw(func))
    return func

class Spacer(Reusable):
    pass

@resource
def spacer(key, parent):
    return Spacer(key, parent)

class LayoutDesc(Detail):
    def __init__(self, func):
        self.func = func

def layout(func):
    parent = context.get()[0]
    parent.contents.append(LayoutDesc(func))
    return func

def static(func):
    parent = context.get()[0]
    assert parent.static is None
    parent.static = func
    return func

def logic(*frames):
    def _decorator_(func):
        parent = context.get()[0]
        assert parent.logic_func is None
        def _impl_(ui, ident, layout, st):
            return func(ui, ident, layout, *(st[s] for s in frames))
        parent.logic_func = _impl_
        return func
    return _decorator_

def shape(func):
    parent = context.get()[0]
    assert parent.shape is None
    parent.shape = func
    return func

def build(ui, root, widget):
    defer = []
    layouter = LayoutEngine(ui, 0, dict(), defer)

    left = layouter[root].left
    bottom = layouter[root].bottom
    width = layouter[root].width
    height = layouter[root].height
    layouter.edit(left, "strong")
    layouter.edit(bottom, "strong")
    layouter.edit(width, "weak")
    layouter.edit(height, "weak")
    layouter.suggest(left, 0)
    layouter.suggest(bottom, 0)
    layouter.suggest(width, widget.width)
    layouter.suggest(height, widget.height)

    layouter.constrain(root)
    layouter.solver.updateVariables()

    current = layouter
    for frame in defer:
        current = LayoutEngine(ui, current.level + 1, current.layouts, defer)
        frame.static(current, frame)
        current.solver.updateVariables()

    def prepare(frame):
        layout = layouter[frame]
        contents = []
        for content in frame.contents:
            if isinstance(content, Draw):
                contents.append(content)
            elif isinstance(content, Frame):
                contents.append(prepare(content))
        return Element(frame, layout.rigid, contents)
    return prepare(root)

class LayoutEngine:
    def __init__(self, ui, level, layouts, defer):
        self.ui = ui
        self.solver = Solver()
        self.level = level
        self.layouts = layouts
        self.defer = defer

    def constrain(self, frame):
        if frame.static:
            self.defer.append(frame)
        else:
            for content in frame.contents:
                if isinstance(content, Spacer):
                    self[content] = Variable()
                if isinstance(content, LayoutDesc):
                    content.func(self, frame)
                if isinstance(content, Frame):
                    self.constrain(content)

    def edit(self, var, strength):
        self.solver.addEditVariable(var, strength)

    def suggest(self, var, value):
        self.solver.suggestValue(var, value)

    def __call__(self, cn):
        self.solver.addConstraint(cn)

    def __getitem__(self, frame):
        try:
            level, layout = self.layouts[frame]
            if self.level <= level:
                return layout
            else:
                return layout.rigid
        except KeyError:
            layout = FlexLayout()
            self.layouts[frame] = self.level, layout
            return layout

    def __setitem__(self, frame, layout):
        assert frame not in self.layouts
        self.layouts[frame] = self.level, layout

class Layout:
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

class FlexLayout(Layout):
    def __init__(self):
        self.left = Variable()
        self.bottom  = Variable()
        self.width  = Variable()
        self.height = Variable()

    @property
    def rigid(self):
        left = self.left.value()
        bottom  = self.bottom.value()
        width = self.width.value()
        height = self.height.value()
        return RigidLayout(left, bottom, width, height)

class RigidLayout(Layout):
    def __init__(self, left, bottom, width, height):
        self.left = left
        self.bottom = bottom
        self.width = width
        self.height = height

    @property
    def rigid(self):
        return self

    @property
    def rect(self):
        return self.left, self.bottom, self.width, self.height

class Element:
    def __init__(self, frame, layout, contents):
        self.frame = frame
        self.layout = layout
        self.contents = contents

    def draw(self, ui, ident):
        ident = ident + [self.frame.key]
        for content in self.contents:
            if isinstance(content, Draw):
                content.func(ui, ident, self)
            elif isinstance(content, Element):
                content.draw(ui, ident)

    def logic(self, ui, ident, transient_state):
        ident = ident + [self.frame.key]
        inside = ui.inside
        hottest = None
        if inside:
            for content in self.contents:
                if isinstance(content, Element):
                    if content.frame.shape(ui.mouse, content.layout.rect):
                        hottest = content
        for content in self.contents:
            if isinstance(content, Element):
                ui.inside = (content is hottest)
                content.logic(ui, ident, transient_state)
        ui.inside = inside
        if self.frame.logic_func:
            transient_state[self.frame] = self.frame.logic_func(ui, ident, self.layout, transient_state)

    #@property
    #def subelements(self):
    #    return [item for item in self.contents if isinstance(item, Element)]

    #def hittest(self, x, y):
    #    return self.shape(x,y, *self.layout.rect)

    #def hit(self, x, y):
    #    if self.hittest(x, y):
    #        selection = self
    #        for content in self.subelements:
    #            selection = content.hit(x, y) or selection
    #        return selection

#class ButtonControl:
#    def __init__(self, ui):
#        self.up = Source(ui.engine)
#        self.down = Source(ui.engine)
#        self.pressed = Source(ui.engine)
#
#class MouseControl:
#    def __init__(self, ui):
#        self.inside = Source(ui.engine)
#        self.enter  = Source(ui.engine)
#        self.leave  = Source(ui.engine)
#        self.left   = ButtonControl(ui)
#        self.middle = ButtonControl(ui)
#        self.right  = ButtonControl(ui)
#        self.motion = Source(ui.engine)
#
#    def by_button_id(self, button):
#        if button == 1:
#            return self.left
#        elif button == 2:
#            return self.middle
#        elif button == 3:
#            return self.right
#
#class KeyboardControl:
#    def __init__(self, ui):
#        self.focus = Source(ui.engine)
#        self.enter = Source(ui.engine)
#        self.leave = Source(ui.engine)
#        self.stream = Source(ui.engine, as_stream)

#class HAlign(Layout):
#    def constrain(self, ui, this, solver):
#        width = this.parent.width
#        solver.addConstraint((this.left == (width - this.width) * self.ratio) | 'strong')
#
#class VAlign(Layout):
#    def constrain(self, ui, this, solver):
#        height = this.parent.height
#        solver.addConstraint((this.bottom == (height - this.height) * self.ratio) | 'strong')
#
def column(spacing = None):
    @layout
    def constrain(cn, this):
        _spacing = Variable() if spacing is None else spacing
        bar0 = bar1 = cn[this].top
        for frame in this.subframes:
            cn(bar1 == cn[frame].top)
            cn(cn[this].left <= cn[frame].left)
            cn(cn[frame].right <= cn[this].right)
            bar0 = cn[frame].bottom
            bar1 = bar0 + _spacing
        cn((bar0 == cn[this].bottom) | 'medium')

def row(spacing = None):
    @layout
    def constrain(cn, this):
        _spacing = Variable() if spacing is None else spacing
        bar0 = bar1 = cn[this].left
        for frame in this.subframes:
            cn(bar1 == cn[frame].left)
            cn(cn[this].bottom <= cn[frame].bottom)
            cn(cn[frame].top <= cn[this].top)
            bar0 = cn[frame].right
            bar1 = bar0 + _spacing
        cn((bar0 == cn[this].right) | 'medium')

Down = namedtuple('Down', ['sym', 'repeat', 'modifiers'])
Up   = namedtuple('Up', ['sym', 'modifiers'])
Text = namedtuple('Text', ['text'])

class GUI:
    def __init__(self, widget, scene, *args, **kwargs):
        self.widget = widget
        self.renderer = sdl2.SDL_GL_CreateContext(widget.window.window)
        self.ctx = moderngl.create_context()
        self.memo = dict()
        self.engine = Engine()

        self.mouse = (0, 0)
        self.buttons = 0
        self.hotitem = None
        self.activeitem = None
        self.activestate = None
        self.focus = None
        self.focusstate = None
        self.lastfocusable = None
        self.keyboard = []
        self.inside = True

        self.clavier = []
        
        assert isinstance(scene, composable)
        self.scene = scene
        self.args   = args
        self.kwargs = kwargs
        token = context.set((None, dict()))
        try:
            self.root = self.scene.invoke(self.scene, self.args, self.kwargs)
            self.element = build(self, self.root, self.widget)
        finally:
            context.reset(token)

        #self.mouse_position = Event()
        #self.pulse = Event()
        #self.now = Hold(sdl2.SDL_GetTicks64() / 1000.0, self.pulse)

        #self.solver = Solver()
        #self.root = scene(self, *args, **kwargs)
        #self.root.attach(self, None)
        #self.reconstrain()

        #self.mouse = MouseControl(self)
        #self.keyboard = KeyboardControl(self)

        #self.keyboard_focus = None
        #self.button_presses = dict()
        #self.under_motion = None

    def mem(self, *args):
        if args not in self.memo:
            self.memo[args] = args[0](self, *args[1:])
        return self.memo[args]

    def resized(self):
        self.element = build(self, self.root, self.widget)
        self.widget.exposed = True

    def draw(self):
        self.ctx.viewport = 0,0,self.widget.width,self.widget.height
        self.ctx.clear(1,1,1,1)
        self.prepare()
        self.element.logic(self, [], dict())
        self.element.draw(self, [])
        self.finish()
        sdl2.SDL_GL_SwapWindow(self.widget.window.window)

    def prepare(self):
        self.hotitem = None
        self.inside = True

    def finish(self):
        if self.buttons == 0:
            self.activeitem = None
            self.activestate = None
        elif self.activeitem is None:
            self.activeitem = (None,)
        self.keyboard.clear()
        self.clavier.clear()

    def update(self):
        self.prepare()
        self.element.logic(self, [], dict())
        self.finish()

        previous = self.root
        token = context.set((None, {self.scene:self.root}))
        try:
            self.root = self.scene.invoke(self.scene, self.args, self.kwargs)
        finally:
            context.reset(token)
        if previous != self.root:
            self.element = build(self, self.root, self.widget)
        self.widget.exposed = (previous != self.root)

    def mouse_motion(self, x, y):
        y = self.widget.height - y
        self.mouse = x, y

    def mouse_button_down(self, x, y, button):
        y = self.widget.height - y
        self.mouse = x, y
        self.buttons |= (1 << (button-1))
 
    def mouse_button_up(self, x, y, button):
        y = self.widget.height - y
        self.mouse = x, y
        self.buttons &= ~(1 << (button-1))
 
    def text_input(self, text):
        action = Text(text)
        self.keyboard.append(action)

    def key_down(self, sym, repeat, modifiers):
        action = Down(sym, repeat, modifiers)
        self.keyboard.append(action)

    def key_up(self, sym, modifiers):
        action = Up(sym, modifiers)
        self.keyboard.append(action)

    def closing(self):
        return True

    def close(self):
        sdl2.SDL_GL_DeleteContext(self.renderer)

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

def circle_fill(color):
    @drawing
    def _circle_filler_(ui, _, this):
        vao, program = ui.mem(circle_filler)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = this.layout.rect
        program['color'] = color
        vao.render(vertices=202, mode=ui.ctx.TRIANGLE_FAN)

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

def circle_stroke(color):
    @drawing
    def _circle_stroke_(ui, _, this):
        vao, program = ui.mem(circle_stroker)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = this.layout.rect
        program['color'] = color
        vao.render(vertices=200*2, mode=ui.ctx.LINES)

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
    
def trace(color):
    @drawing
    def _trace_draw_(ui, _, this):
        vao, program = ui.mem(rectangle_stroker)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = this.layout.rect
        program['color'] = color
        vao.render(vertices=8, mode=ui.ctx.LINES)

def fill(color):
    @drawing
    def _fill_draw_(ui, _, this):
        vao, program = ui.mem(rectangle_filler)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = this.layout.rect
        program['color'] = color
        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
