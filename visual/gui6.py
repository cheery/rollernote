from poga.libpoga_capi import *
from collections import namedtuple
from contextlib import contextmanager
from contextvars import ContextVar
#from .font import FontEngine
import numpy as np
import sdl2
import moderngl
import typing

context = ContextVar('context')
ui      = ContextVar('ui')

class Tag:
    pass

class NodeMetaclass(type):
    def __call__(cls, *args, _attach_=True, **kwargs):
        node = super().__call__(*args, **kwargs)
        if _attach_:
            context.get().add_child(node)
            return NodeContextManager(node)
        else:
            return node

class Node(metaclass=NodeMetaclass):
    def __init__(self, name=None, rect=None, scroll=(0,0)):
        if name is None:
            self.name = Tag()
        else:
            self.name = name
        self.children = {}
        self.parent = None
        self.node = YGNodeNew()
        self.pending_signals = []
        self.pending_children = False
        for _name, _cls in typing.get_type_hints(type(self)).items():
            if _cls is Signal and not hasattr(self, _name):
                setattr(self, _name, _cls())

        #self.rect = rect
        #self.layout = layout
        #self.computed_size = None
        #self.scroll = scroll
        self.mouse_visible = True

    @property
    def rect(self):
        if self.parent is None:
            return Rect(
                YGNodeLayoutGetLeft(self.node),
                YGNodeLayoutGetBottom(self.node),
                YGNodeLayoutGetWidth(self.node),
                YGNodeLayoutGetHeight(self.node))
        else:
            parent_height = YGNodeLayoutGetHeight(self.parent.node)
            height = YGNodeLayoutGetHeight(self.node)
            return Rect(
                YGNodeLayoutGetLeft(self.node),
                parent_height - height - YGNodeLayoutGetTop(self.node),
                YGNodeLayoutGetWidth(self.node),
                height)

    @property
    def global_rect(self):
        rect = self.rect
        parent = self.parent
        while parent:
            left, bottom, _, _ = parent.rect
            rect = rect.offset(left, bottom)
            parent = parent.parent
        return rect

    def add_child(self, child):
        child.parent = self
        YGNodeInsertChild(self.node, child.node, len(self.children))
        assert child.name not in self, "duplicate name"
        self.children[child.name] = child

    def insert_child(self, child, index):
        child.parent = self
        YGNodeInsertChild(self.node, child.node, index)
        assert child.name not in self, "duplicate name"
        self.children[child.name] = child

    def swap_child(self, child, index):
        child.parent = self
        YGNodeSwapChild(self.node, child.node, index)
        assert child.name in self, "child must be there for a swap"
        self.children[child.name] = child

    def detach(self):
        YGNodeRemoveChild(self.parent.node, self.node)
        self.parent.children.pop(self.name)
        self.parent = None

    def __del__(self):
        YGNodeFree(self.node)

    def draw(self, ui, x, y):
        x1, y1 = x + self.rect.left, y + self.rect.bottom
        mouse = ui.mouse[0] - x1, ui.mouse[1] - y1
        self.pre_draw(ui, x, y)
        inside = ui.inside
        cover = None
        if inside:
            for child in self:
                if child.mouse_visible and box(mouse, child.rect):
                    cover = child
        for child in self:
            ui.inside = child is cover
            child.draw(ui, x1, y1)
        ui.inside = None is cover
        self.post_draw(ui, x, y)
        ui.inside = inside
        #trace(ui, (1,0,1,1), self.rect.offset(x, y))

    def pre_draw(self, ui, x, y):
        pass

    def post_draw(self, ui, x, y):
        pass

    #def get_size(self, ui, available_width, available_height):
    #    if self.layout is None:
    #        return None
    #    self.layout.measure(ui, self, available_width, available_height)
    #    return self.computed_size

    #def do_layout(self, ui, computed=False):
    #    if not computed:
    #        assert self.layout is None
    #    left, bottom, width, height = self.rect.offset(*self.scroll)
    #    for child in self:
    #        if child.layout is None:
    #            child.do_layout(ui)
    #        elif child.layout.absolute:
    #            w, h = child.get_size(ui, width, height)
    #            x = child.layout.absolute[0](0, w, width)
    #            y = child.layout.absolute[1](0, h, height)
    #            shape = Rect(x, y, w, h)
    #            child.layout.do(ui, child, shape)
    #        else:
    #            w, h = child.get_size(ui, width, height)
    #            shape = Rect(0, 0, *child.computed_size)
    #            child.layout.do(ui, child, shape)

    def __contains__(self, item):
        return item in self.children

    def __getitem__(self, name):
        return self.children[name]

    def __len__(self):
        return len(self.children)

    def __iter__(self):
        return iter(self.children.values())

    def traverse(self, results=None):
        if results is None:
            results = []
        for node in self:
            results.append(node)
            node.traverse(results)
        return results

    @property
    def root(self):
        root = self
        while root.parent:
            root = root.parent
        return root

def prefab(constructor=Node, *nargs, **nkwargs):
    def _decorator_(func):
        def _prefab_(*args, **kwargs):
            this = constructor(*nargs, _attach_=False, **nkwargs)
            token = context.set(this)
            try:
                func(*args, **kwargs)
            finally:
                context.reset(token)
            return this
        return _prefab_
    return _decorator_

class NodeContextManager:
    def __init__(self, node):
        self.node = node
        self.token = None

    def __enter__(self):
        self.token = context.set(self.node)
        return self.node

    def __exit__(self, exc_type, exc_value, traceback):
        context.reset(self.token)

class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        if slot not in self._slots:
            self._slots.append(slot)

    def disconnect(self, slot):
        if slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args, **kwargs):
        for slot in self._slots:
            slot(*args, **kwargs)

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
    def __init__(self, left, bottom, width, height):
        self.left = left
        self.bottom = bottom
        self.width = width
        self.height = height

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

    def __iter__(self):
        return iter((self.left, self.bottom, self.width, self.height))

    def offset(self, x, y):
        return Rect(x + self.left, y + self.bottom, self.width, self.height)

KeyDown = namedtuple('KeyDown', ['sym', 'repeat', 'modifiers'])
KeyUp   = namedtuple('KeyUp', ['sym', 'modifiers'])
KeyText = namedtuple('KeyText', ['text'])

class GUI:
    def __init__(self, widget, scene):
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
        self.activedrag = None
        self.focus = None
        self.focusstate = None
        self.lastfocusable = None
        self.keyboard = []

        self.clavier = []

        #self.scroll_x = 0
        #self.scroll_y = 0

        self.queued = []

        self.scene = scene
        self.do_layout()
        #self.scene.rect = Rect(0,0,self.widget.width,self.widget.height)
        #self.scene.do_layout(self)

        #self.solver = Solver()
        #self.lay = dict()

        #with open(scene_filename, 'r') as fd:
        #    program = dataui.parser.parse(fd.read())
        #if program is None:
        #    raise Exception("could not load ui program")

        #self.program = program
        #self.storage = storage

    def queue(self, fn, *args, **kwargs):
        self.queued.append((fn, args, kwargs))

    def do_layout(self):
        token = ui.set(self)
        try:
            YGNodeCalculateLayout(self.scene.node,
                                  self.widget.width,
                                  self.widget.height,
                                  LTR)
        finally:
            ui.reset(token)
        
    def mem(self, *args):
        if args not in self.memo:
            self.memo[args] = args[0](self, *args[1:])
        return self.memo[args]

    def resized(self):
        self.widget.exposed = True
        self.do_layout()

    def draw(self):
        if YGNodeIsDirty(self.scene.node):
            self.do_layout()

        self.ctx.viewport = 0,0,self.widget.width,self.widget.height
        self.ctx.clear(1,1,1,1)

        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_equation = self.ctx.FUNC_ADD
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA

        self.prepare()
        self.scene.draw(self, 0, 0)
        #store = dataui.evaluator.Store(self.storage.copy())
        #def interact(store):
        #    ui = self
        #    draggable_set = store.data.get('draggable', [])
        #    button_set = store.data.get('button', [])
        #    t_hover = dataui.evaluator.Term('hover', ())
        #    t_click = dataui.evaluator.Term('click', ())
        #    store.data.setdefault('on', set())
        #    for ident, rect in store.data.get('present', []):
        #        if box(self.mouse, rect) and self.hotitem is None:
        #            self.hotitem = ident
        #            store.data['on'].add((t_hover, ident))
        #            if ui.activeitem is None and ui.buttons == 1:
        #                ui.activeitem = ident
        #                ui.activestate = ui.mouse
        #        if ui.activeitem == ident and ui.buttons > 0 and (ident,) in draggable_set:
        #            dx = ui.mouse[0] - ui.activestate[0]
        #            dy = ui.mouse[1] - ui.activestate[1]
        #            t_drag = dataui.evaluator.Term('drag', (dx, dy))
        #            store.data['on'].add((t_drag, ident))
        #        if ui.activeitem == ident and ui.buttons == 0 and (ident,) in draggable_set:
        #            dx = ui.mouse[0] - ui.activestate[0]
        #            dy = ui.mouse[1] - ui.activestate[1]
        #            t_drop = dataui.evaluator.Term('drop', (dx, dy))
        #            store.data['on'].add((t_drop, ident))
        #        if ui.activeitem == ident and ui.buttons == 0 and (ident,) in button_set:
        #            store.data['on'].add((t_click, ident))
        #        
        #stages = {'on': (interact, ['present', 'button', 'draggable'])}
        #dataui.evaluator.run_program(self.program, store, stages)
        self.finish()
        queued, self.queued = self.queued, []
        for fn, args, kwargs in queued:
            fn(*args, **kwargs)

        #for color, rect in store.data.get('rectangle', set()):
        #    fill(self, color, rect)

        #for color, pos, r in store.data.get('circle', set()):
        #    circle_fill(self, color, (pos[0] - r, pos[1] - r, r*2, r*2))

        #for color, pos0, pos1 in store.data.get('line', set()):
        #    ui = self
        #    program, vao, buffer, data = ui.mem(line_draw_setup)
        #    program['scroll'] = ui.scroll_x, ui.scroll_y
        #    program['size'] = ui.widget.width, ui.widget.height
        #    program['color'] = color
        #    data[0] = pos0[0]
        #    data[1] = pos0[1]
        #    data[2] = pos1[0]
        #    data[3] = pos1[1]
        #    buffer.write(data)
        #    vao.render(mode=ui.ctx.LINES)


        #font = self.mem(FontEngine, int(16))
        #for text, (x,y) in store.data.get('text', set()):
        #    font.prepare((0,0,0,1))
        #    font.text(text, x, y)
        #    font.finish()

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
        #elif self.activeitem is None:
        #    self.activeitem = (None,)
        #    self.activestate = self.mouse
        #if self.activeitem == (None,):
        #    x, y = self.activestate
        #    px,py = self.screen_mouse
        #    self.scroll_x = x - px
        #    self.scroll_y = y - py
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
        #self.mouse = x + self.scroll_x, y + self.scroll_y
        self.mouse = x, y

    def mouse_button_down(self, x, y, button):
        y = self.widget.height - y
        self.screen_mouse = x, y
        #self.mouse = x + self.scroll_x, y + self.scroll_y
        self.mouse = x, y
        self.buttons |= (1 << (button-1))
 
    def mouse_button_up(self, x, y, button):
        y = self.widget.height - y
        self.screen_mouse = x, y
        #self.mouse = x + self.scroll_x, y + self.scroll_y
        self.mouse = x, y
        self.buttons &= ~(1 << (button-1))
 
    def text_input(self, text):
        action = KeyText(text)
        self.keyboard.append(action)

    def key_down(self, sym, repeat, modifiers):
        action = KeyDown(sym, repeat, modifiers)
        self.keyboard.append(action)

    def key_up(self, sym, modifiers):
        action = KeyUp(sym, modifiers)
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
    program['scroll'] = 0, 0 #ui.scroll_x, ui.scroll_y
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
    program['scroll'] = 0, 0
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
    program['scroll'] = 0, 0 #ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
    program['color'] = color
    vao.render(vertices=8, mode=ui.ctx.LINES)

def fill(ui, color, rect):
    vao, program = ui.mem(rectangle_filler)
    program['scroll'] = 0, 0 #ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['rect'] = rect
    program['color'] = color
    vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)

# class Flex:
#     def __init__(self, minimum):
#         self.minimum = minimum
# 
# def is_flexible(item):
#     return isinstance(item, Flex)
# 
# def squish(flex):
#     if is_flexible(flex):
#         return flex.minimum
#     return flex
#     
# def align_low(pos, space, available_space):
#     return pos
# 
# def align_middle(pos, space, available_space):
#     return pos + available_space / 2 - space / 2
# 
# def align_high(pos, space, available_space):
#     return pos + available_space - space
# 
# class Box:
#     def __init__(self, width=0, height=0, absolute=None):
#         self.width = width
#         self.height = height
#         self.absolute = absolute
# 
#     def measure(self, ui, node, available_width, available_height):
#         if is_flexible(self.width):
#             calc_width = max(self.width.minimum, available_width)
#         else:
#             calc_width = self.width
#         if is_flexible(self.height):
#             calc_height = max(self.height.minimum, available_height)
#         else:
#             calc_height = self.height
#         node.computed_size = calc_width, calc_height
# 
#     def do(self, ui, node, rect, shallow=True):
#         node.rect = rect
#         node.do_layout(ui, computed=True)
# 
# class HBox(Box):
#     def __init__(self, align = align_high, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.align = align
# 
#     def measure(self, ui, node, available_width, available_height):
#         if not is_flexible(self.width):
#             available_width = self.width
#         if not is_flexible(self.height):
#             available_height = self.height
#         total_width = 0
#         max_height = 0
#         flexibles = []
#         for child in node:
#             if child.layout is None:
#                 continue
#             if child.layout.absolute:
#                 child.get_size(ui, available_width, available_height)
#                 continue
#             if is_flexible(child.layout.width) and is_flexible(self.width):
#                 flexibles.append(child)
#             else:
#                 width, height = child.get_size(ui, squish(child.layout.width), available_height)
#                 total_width += width
#                 max_height = max(max_height, height)
#         if flexibles:
#             remaining_width = available_width - total_width
#             flexible_width = remaining_width / len(flexibles)
#             for child in flexibles:
#                 width, height = child.get_size(ui, flexible_width, available_height)
#                 total_width += width
#                 max_height = max(max_height, height)
#         if is_flexible(self.width):
#             calc_width = max(self.width.minimum, total_width, available_width)
#         else:
#             calc_width = max(self.width, total_width)
#         if is_flexible(self.height):
#             calc_height = max(self.height.minimum, max_height, available_height)
#         else:
#             calc_height = max(self.height, max_height)
#         node.computed_size = calc_width, calc_height
# 
#     def do(self, ui, this, rect, shallow=True):
#         this.rect = rect
#         current_x = this.scroll[0]
#         for child in this:
#             if child.layout is None:
#                 child.do_layout(ui)
#             elif child.layout.absolute:
#                 width, height = child.computed_size
#                 x = child.layout.absolute[0](this.scroll[0], width, rect.width)
#                 y = child.layout.absolute[1](this.scroll[1], height, rect.height)
#                 shape = Rect(x, y, width, height)
#                 child.layout.do(child, shape)
#             elif child.layout is not None:
#                 width, height = child.computed_size
#                 current_y = self.align(0, height, rect.height)
#                 shape = Rect(current_x, current_y, width, height)
#                 child.layout.do(ui, child, shape)
#                 current_x += width
# 
# class VBox(Box):
#     def __init__(self, align = align_low, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.align = align
# 
#     def measure(self, ui, node, available_width, available_height):
#         if not is_flexible(self.width):
#             available_width = self.width
#         if not is_flexible(self.height):
#             available_height = self.height
#         total_height = 0
#         max_width = 0
#         flexibles = []
#         for child in node:
#             if child.layout is None:
#                 continue
#             if child.layout.absolute:
#                 child.get_size(ui, available_width, available_height)
#                 continue
#             if is_flexible(child.layout.height) and is_flexible(self.height):
#                 flexibles.append(child)
#             else:
#                 width, height = child.get_size(ui, available_width, squish(child.layout.height))
#                 total_height += height
#                 max_width = max(max_width, width)
#         if flexibles:
#             remaining_height = available_height - total_height
#             flexible_height = remaining_height / len(flexibles)
#             for child in flexibles:
#                 width, height = child.get_size(ui, available_width, flexible_height)
#                 total_height += height
#                 max_width = max(max_width, width)
# 
#         if is_flexible(self.width):
#             calc_width = max(self.width.minimum, max_width, available_width)
#         else:
#             calc_width = max(self.width, max_width)
#         if is_flexible(self.height):
#             calc_height = max(self.height.minimum, total_height, available_height)
#         else:
#             calc_height = max(self.height, total_height)
#         node.computed_size = calc_width, calc_height
# 
#     def do(self, ui, this, rect, shallow=True):
#         this.rect = rect
#         current_y = rect.height + this.scroll[1]
#         for child in this:
#             if child.layout is None:
#                 child.do_layout(ui)
#             elif child.layout.absolute:
#                 width, height = child.computed_size
#                 x = child.layout.absolute[0](this.scroll[0], width, rect.width)
#                 y = child.layout.absolute[1](this.scroll[1], height, rect.height)
#                 shape = Rect(x, y, width, height)
#                 child.layout.do(ui, child, shape)
#             elif child.layout is not None:
#                 width, height = child.computed_size
#                 current_x = self.align(this.scroll[0], width, rect.width)
#                 current_y -= height
#                 shape = Rect(current_x, current_y, width, height)
#                 child.layout.do(ui, child, shape)
# 
# class Padding(Box):
#     def __init__(self, top=0, right=0, bottom=0, left=0):
#         super().__init__()
#         self.top = top
#         self.right = right
#         self.bottom = bottom
#         self.left = left
# 
#     def measure(self, ui, node, available_width, available_height):
#         calc_width = 0
#         calc_height = 0
#         for child in node:
#             if child.layout is None:
#                 continue
#             width, height = child.get_size(ui, available_width, available_height)
#             calc_width = max(calc_width, width)
#             calc_height = max(calc_height, height)
#         calc_width = calc_width + self.left + self.right
#         calc_height = calc_height + self.top + self.bottom
#         node.computed_size = calc_width, calc_height
# 
#     def do(self, ui, this, rect, shallow=True):
#         if shallow:
#             this.rect = rect
#         rect = Rect(
#             self.left + this.scroll[0],
#             self.bottom + this.scroll[1],
#             this.computed_size[0] - self.left - self.right,
#             this.computed_size[0] - self.bottom - self.top)
#         for child in this:
#             if child.layout is None:
#                 child.do_layout(ui)
#             elif child.layout.absolute:
#                 width, height = child.computed_size
#                 x = child.layout.absolute[0](0, width, rect.width)
#                 y = child.layout.absolute[1](0, height, rect.height)
#                 shape = Rect(x, y, width, height)
#                 child.layout.do(ui, child, shape)
#             else:
#                 width, height = child.computed_size
#                 shape = Rect(self.left, self.bottom, width, height)
#                 child.layout.do(ui, child, shape)
# 
# #     def __init__(self, inner, state, *args, **kwargs):
# #         super().__init__(*args, **kwargs)
# #         self.inner = inner
# #         self.scroll_x = state.scroll_x
# #         self.scroll_y = state.scroll_y
# #         self.scale_x = state.scale_x
# #         self.scale_y = state.scale_y
# # 
# #     def measure(self, children, available_width, available_height):
# #         if self.flexible_width:
# #             self.calc_width = available_width
# #         else:
# #             self.calc_width = self.width
# #         if self.flexible_height:
# #             self.calc_height = available_height
# #         else:
# #             self.calc_height = self.height
# #         self.inner.measure(children,
# #             self.calc_width / self.scale_x,
# #             self.calc_height / self.scale_y)
# # 
# #     def max_scroll(self):
# #         max_scroll_x = max(0, self.inner.calc_width - self.calc_width/self.scale_x)
# #         max_scroll_y = max(0, self.inner.calc_height - self.calc_height/self.scale_y)
# #         return max_scroll_x, max_scroll_y
# # 
# #     def clamp_scroll(self, scroll_x, scroll_y):
# #         max_scroll_x, max_scroll_y = self.max_scroll()
# # 
# #         # Adjust scroll positions to be within the valid range
# #         scroll_x = max(0, min(scroll_x, max_scroll_x))
# #         scroll_y = max(0, min(scroll_y, max_scroll_y))
# #         return scroll_x, scroll_y
# # 
# #     def __call__(self, this, box, shallow=True):
# #         assert shallow
# #         matrix = cairo.Matrix()
# #         matrix.translate(box.x, box.y)
# #         matrix.scale(self.scale_x, self.scale_y)
# #         matrix.translate(-self.scroll_x, -self.scroll_y)
# #         this.transform = matrix
# #         this.shape = box
# #         inner_box = Box(0, 0, self.inner.calc_width, self.inner.calc_height)
# #         self.inner(this, inner_box, shallow=False)

# MeasureMode: Undefined, Exactly, AtMost
# NodeType: Default, Text
# Direction: Inherit, LTR, RTL
# FlexDirection: Column, ColumnReverse, Row, RowReverse
# Align: Auto, FlexStart, Center, FlexEnd, Stretch, Baseline, SpaceBetween, SpaceAround
# PositionType: Static, Relative, Absolute
# Wrap: NoWrap, Wrap, WrapReverse
# Justify: FlexStart, Center, FlexEnd, SpaceBetween, SpaceAround, SpaceEvenly
# Overflow: Visible, Hidden, Scroll
# Display: Flex, DisplayNone
# Edge: Left, Top, Right, Bottom, Start, End, Horizontal, Vertical, All
# Unit: Undefined, Point, Percent, Auto
# YGValue(value, unit)
# LogLevel: Error, Warn, Info, Debug, Verbose, Fatal

def width(width):
    YGNodeStyleSetWidth(context.get().node, width)

def width_auto():
    YGNodeStyleSetWidthAuto(context.get().node)

def width_percent(width):
    YGNodeStyleSetWidthPercent(context.get().node, width)

def height(height):
    YGNodeStyleSetHeight(context.get().node, height)

def height_auto():
    YGNodeStyleSetHeightAuto(context.get().node)

def height_percent(height):
    YGNodeStyleSetHeightPercent(context.get().node, height)

def flex_direction(direction):
    YGNodeStyleSetFlexDirection(context.get().node, direction)

def flex(flex):
    YGNodeStyleSetFlex(context.get().node, flex)

def align_content(align):
    YGNodeStyleSetAlignContent(context.get().node, align)

def align_items(align):
    YGNodeStyleSetAlignItems(context.get().node, align)

def align_self(align):
    YGNodeStyleSetAlignSelf(context.get().node, align)

def aspect_ratio(ratio):
    YGNodeStyleSetAspectRatio(context.get().node, ratio)

def border(width):
    YGNodeStyleSetBorder(context.get().node, width)

def direction(direction):
    YGNodeStyleSetDirection(context.get().node, direction)

def display(display):
    YGNodeStyleSetDisplay(context.get().node, display)

def flex_basis(basis):
    YGNodeStyleSetFlexBasis(context.get().node, basis)

def flex_basis_auto():
    YGNodeStyleSetFlexBasisAuto(context.get().node)

def flex_basis_percent(basis):
    YGNodeStyleSetFlexBasisPercent(context.get().node, basis)

def flex_grow(grow):
    YGNodeStyleSetFlexGrow(context.get().node, grow)

def flex_shrink(shrink):
    YGNodeStyleSetFlexShrink(context.get().node, shrink)

def flex_wrap(wrap):
    YGNodeStyleSetFlexWrap(context.get().node, wrap)

def justify_content(jc):
    YGNodeStyleSetJustifyContent(context.get().node, jc)

def margin(edge, value):
    YGNodeStyleSetMargin(context.get().node, edge, value)

def margin_auto(edge, value):
    YGNodeStyleSetMarginAuto(context.get().node, edge)

def margin_percent(edge, value):
    YGNodeStyleSetMarginPercent(context.get().node, edge, value)

def max_height(height):
    YGNodeStyleSetMaxHeight(context.get().node, height)

def max_height_percent(height):
    YGNodeStyleSetMaxHeightPercent(context.get().node, height)

def max_width(width):
    YGNodeStyleSetMaxWidth(context.get().node, width)

def max_width_percent(width):
    YGNodeStyleSetMaxWidthPercent(context.get().node, width)

def min_height(height):
    YGNodeStyleSetMinHeight(context.get().node, height)

def min_height_percent(height):
    YGNodeStyleSetMinHeightPercent(context.get().node, height)

def min_width(width):
    YGNodeStyleSetMinWidth(context.get().node, width)

def min_width_percent(width):
    YGNodeStyleSetMinWidthPercent(context.get().node, width)

def overflow(ovf):
    YGNodeStyleSetOverflow(context.get().node, ovf)

def padding(edge, value):
    YGNodeStyleSetPadding(context.get().node, edge, value)

def padding_percent(edge, value):
    YGNodeStyleSetPaddingPercent(context.get().node, edge, value)

def position(edge, pos):
    YGNodeStyleSetPosition(context.get().node, edge, pos)

def position_percent(edge, pos):
    YGNodeStyleSetPositionPercent(context.get().node, edge, pos)

def position_type(position_type):
    YGNodeStyleSetPositionType(context.get().node, position_type)

# YGNodeSetBaselineFunc
# (noderef, a, b) -> c
