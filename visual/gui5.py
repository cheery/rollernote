#from kiwisolver import Variable, Solver
from reaction import *
from collections import namedtuple
from contextvars import ContextVar
from .font import FontEngine
import numpy as np
import sdl2
import moderngl

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

class Rect:
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

class FlexRect(Rect):
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
        return RigidRect(left, bottom, width, height)

class RigidRect(Rect):
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

Down = namedtuple('Down', ['sym', 'repeat', 'modifiers'])
Up   = namedtuple('Up', ['sym', 'modifiers'])
Text = namedtuple('Text', ['text'])

#import dataui.parser
#import dataui.evaluator

class GUI:
    def __init__(self, widget, scene_filename, storage):
        self.widget = widget
        self.renderer = sdl2.SDL_GL_CreateContext(widget.window.window)
        self.ctx = moderngl.create_context()
        self.memo = dict()

        self.screen_mouse = (0,0)
        self.mouse = (0, 0)
        self.buttons = 0
        self.hotitem = None
        self.activeitem = None
        self.activestate = None
        self.focus = None
        self.focusstate = None
        self.lastfocusable = None
        self.keyboard = []

        self.clavier = []

        self.scroll_x = 0
        self.scroll_y = 0

        #self.solver = Solver()
        #self.lay = dict()

        with open(scene_filename, 'r') as fd:
            program = dataui.parser.parse(fd.read())
        if program is None:
            raise Exception("could not load ui program")

        self.program = program
        self.storage = storage
        
    def mem(self, *args):
        if args not in self.memo:
            self.memo[args] = args[0](self, *args[1:])
        return self.memo[args]

    def resized(self):
        self.widget.exposed = True

    def draw(self):
        self.ctx.viewport = 0,0,self.widget.width,self.widget.height
        self.ctx.clear(1,1,1,1)
        self.prepare()
        store = dataui.evaluator.Store(self.storage.copy())
        def interact(store):
            ui = self
            draggable_set = store.data.get('draggable', [])
            button_set = store.data.get('button', [])
            t_hover = dataui.evaluator.Term('hover', ())
            t_click = dataui.evaluator.Term('click', ())
            store.data.setdefault('on', set())
            for ident, rect in store.data.get('present', []):
                if box(self.mouse, rect) and self.hotitem is None:
                    self.hotitem = ident
                    store.data['on'].add((t_hover, ident))
                    if ui.activeitem is None and ui.buttons == 1:
                        ui.activeitem = ident
                        ui.activestate = ui.mouse
                if ui.activeitem == ident and ui.buttons > 0 and (ident,) in draggable_set:
                    dx = ui.mouse[0] - ui.activestate[0]
                    dy = ui.mouse[1] - ui.activestate[1]
                    t_drag = dataui.evaluator.Term('drag', (dx, dy))
                    store.data['on'].add((t_drag, ident))
                if ui.activeitem == ident and ui.buttons == 0 and (ident,) in draggable_set:
                    dx = ui.mouse[0] - ui.activestate[0]
                    dy = ui.mouse[1] - ui.activestate[1]
                    t_drop = dataui.evaluator.Term('drop', (dx, dy))
                    store.data['on'].add((t_drop, ident))
                if ui.activeitem == ident and ui.buttons == 0 and (ident,) in button_set:
                    store.data['on'].add((t_click, ident))
                
        stages = {'on': (interact, ['present', 'button', 'draggable'])}
        dataui.evaluator.run_program(self.program, store, stages)
        self.finish()

        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_equation = self.ctx.FUNC_ADD
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA

        for color, rect in store.data.get('rectangle', set()):
            fill(self, color, rect)

        for color, pos, r in store.data.get('circle', set()):
            circle_fill(self, color, (pos[0] - r, pos[1] - r, r*2, r*2))

        for color, pos0, pos1 in store.data.get('line', set()):
            ui = self
            program, vao, buffer, data = ui.mem(line_draw_setup)
            program['scroll'] = ui.scroll_x, ui.scroll_y
            program['size'] = ui.widget.width, ui.widget.height
            program['color'] = color
            data[0] = pos0[0]
            data[1] = pos0[1]
            data[2] = pos1[0]
            data[3] = pos1[1]
            buffer.write(data)
            vao.render(mode=ui.ctx.LINES)


        font = self.mem(FontEngine, int(16))
        for text, (x,y) in store.data.get('text', set()):
            font.prepare((0,0,0,1))
            font.text(text, x, y)
            font.finish()

        sdl2.SDL_GL_SwapWindow(self.widget.window.window)

        #for name in store.data:
        #    for row in store.data[name]:
        #        print(name, row)

    def prepare(self):
        self.hotitem = None
        self.inside = True

    def finish(self):
        if self.buttons == 0:
            self.activeitem = None
            self.activestate = None
        elif self.activeitem is None:
            self.activeitem = (None,)
            self.activestate = self.mouse
        if self.activeitem == (None,):
            x, y = self.activestate
            px,py = self.screen_mouse
            self.scroll_x = x - px
            self.scroll_y = y - py
        self.keyboard.clear()
        self.clavier.clear()

        #w = self.element.layout.width - self.widget.width
        #h = self.element.layout.height - self.widget.height
        #self.scroll_x = max(0, min(w, self.scroll_x))
        #self.scroll_y = max(0, min(h, self.scroll_y))

    def update(self):
        self.widget.exposed = True

    def mouse_motion(self, x, y):
        y = self.widget.height - y
        self.screen_mouse = x, y
        self.mouse = x + self.scroll_x, y + self.scroll_y

    def mouse_button_down(self, x, y, button):
        y = self.widget.height - y
        self.screen_mouse = x, y
        self.mouse = x + self.scroll_x, y + self.scroll_y
        self.buttons |= (1 << (button-1))
 
    def mouse_button_up(self, x, y, button):
        y = self.widget.height - y
        self.screen_mouse = x, y
        self.mouse = x + self.scroll_x, y + self.scroll_y
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
        uniform vec2 scroll;
        uniform vec2 size;
        vec2 pixel_to_screen(vec2 pixel) {
            return (pixel - scroll) / size * 2.0 - 1.0;
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

def line_draw_setup(ui):
   program = ui.mem(plain_line_program)
   data = np.full(4, 0.0, dtype=np.float32)
   buffer = ui.ctx.buffer(data)
   vao = ui.ctx.vertex_array(program, buffer, 'point')
   return program, vao, buffer, data

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

def circle_fill(ui, color, rect):
    vao, program = ui.mem(circle_filler)
    program['scroll'] = ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
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

def circle_stroke(ui, color, rect):
    vao, program = ui.mem(circle_stroker)
    program['scroll'] = ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
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
    
def trace(ui, color, rect):
    vao, program = ui.mem(rectangle_stroker)
    program['scroll'] = ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
    program['color'] = color
    vao.render(vertices=8, mode=ui.ctx.LINES)

def fill(ui, color, rect):
    vao, program = ui.mem(rectangle_filler)
    program['scroll'] = ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
    program['color'] = color
    vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
