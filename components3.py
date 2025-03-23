from reaction import *
from visual import gui6
from visual.font import FontEngine
from aural.box import On, Off
from collections import namedtuple
import sdl2
import math
import numpy as np
import moderngl

class InsideScrollable(gui6.Node):
    @property
    def rect(self):
        srect = super().rect
        if gui6.YGNodeLayoutGetHadOverflow(self.node):
            rects = [child.rect for child in self]
            width  = max((rect.right for rect in rects), default=0)
            height = max((rect.top   for rect in rects), default=0)
            width  += gui6.YGNodeLayoutGetPadding(self.node, gui6.Right)
            height += gui6.YGNodeLayoutGetPadding(self.node, gui6.Top)
            return gui6.Rect(srect.left, srect.bottom, max(width, srect.width), max(height, srect.height))
        else:
            return srect

class Scrollable(gui6.Node):
    def __init__(self, *args, horizontal=True, vertical=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.horizontal = horizontal
        self.vertical = vertical
        self.scroll_x = 0
        self.scroll_y = 0
        with gui6.NodeContextManager(self):
            gui6.overflow(gui6.Scroll)
            gui6.padding(gui6.All, 0)
            if self.horizontal:
                gui6.padding(gui6.Bottom, 20)
            if self.vertical:
                gui6.padding(gui6.Right, 20)

    def pre_draw(self, ui, x, y):
        self.screen_width = gui6.YGNodeLayoutGetWidth(self.node) - 20 * self.vertical
        self.screen_height = gui6.YGNodeLayoutGetHeight(self.node) - 20 * self.horizontal
        rects = [child.rect for child in self]
        left   = min((rect.left   for rect in rects), default=0)
        right  = max((rect.right  for rect in rects), default=1)
        top    = max((rect.top    for rect in rects), default=1)
        bottom = min((rect.bottom for rect in rects), default=0)
        self.content_width = right - left
        #self.content_width += gui6.YGNodeLayoutGetPadding(self.node, gui6.Right)
        #self.content_width += gui6.YGNodeLayoutGetPadding(self.node, gui6.Left)
        self.content_height = top - bottom
        #self.content_height += gui6.YGNodeLayoutGetPadding(self.node, gui6.Top)
        #self.content_height += gui6.YGNodeLayoutGetPadding(self.node, gui6.Bottom)

        rect = super().rect.offset(x, y)
        xbar = gui6.Rect(rect.left, rect.bottom, rect.width - 20, 20)
        xin = xbar.outset(-2, -2)
        ybar = gui6.Rect(rect.right - 20, rect.bottom + 20, 20, rect.height - 20)
        yin = ybar.outset(-2, -2)
        xhandle_width = 10 + (xin.width - 10) * min(1.0, self.screen_width / self.content_width)
        if self.content_width - self.screen_width > 0:
            xhandle_ratio = (-self.scroll_x / (self.content_width - self.screen_width))
        else:
            xhandle_ratio = 0
        xhandle_offset = (xin.width - xhandle_width) * xhandle_ratio
        xhandle = gui6.Rect(xin.left + xhandle_offset, xin.bottom, xhandle_width, xin.height)
        if self.horizontal:
            gui6.fill(ui, (1,1,1,1), xbar)
            gui6.fill(ui, (0,0,0,1), xhandle)
        yhandle_height = 10 + (yin.height - 10) * min(1.0, self.screen_height / self.content_height)
        if self.content_height - self.screen_height > 0:
            yhandle_ratio = (-self.scroll_y / (self.content_height - self.screen_height))
        else:
            yhandle_ratio = 0
        yhandle_offset = (yin.height - yhandle_height) * yhandle_ratio
        yhandle = gui6.Rect(yin.left, yin.top - yhandle_height - yhandle_offset, yin.width, yhandle_height)
        if self.vertical:
            gui6.fill(ui, (1,1,1,1), ybar)
            gui6.fill(ui, (0,0,0,1), yhandle)

        if ui.inside:
            ui.hotitem = self
            if ui.activeitem is None and ui.buttons > 0 and self.horizontal and gui6.box(ui.mouse, xhandle):
                ui.activeitem = self
                ui.activestate = ui.mouse, True
            if ui.activeitem is None and ui.buttons > 0 and self.vertical and gui6.box(ui.mouse, yhandle):
                ui.activeitem = self
                ui.activestate = ui.mouse, False
        if ui.activeitem is self and ui.buttons > 0:
            (px, py), in_xhandle = ui.activestate
            mx, my = ui.mouse
            ui.activestate = ui.mouse, in_xhandle
            if in_xhandle:
                self.scroll_x = self.scroll_x - (mx - px) * (self.content_width - self.screen_width) / (xbar.width - xhandle.width)
                self.scroll_x = max(self.scroll_x, -(self.content_width - self.screen_width))
                self.scroll_x = min(0, self.scroll_x)
            else:
                self.scroll_y = self.scroll_y + (my - py) * (self.content_height - self.screen_height) / (ybar.height - yhandle.height)
                self.scroll_y = max(self.scroll_y, -(self.content_height - self.screen_height))
                self.scroll_y = min(0, self.scroll_y)

                #self.scroll_x = self.scroll_x + (mx - px)

    @property
    def irect(self):
        return self.rect.offset(self.scroll_x, -self.scroll_y)

    @property
    def srect(self):
        left, bottom, width, height = self.rect
        return gui6.Rect(left, bottom+20, width-20, height-20)

    def draw(self, ui, x, y):
        self_rect = self.rect
        self_irect = self.irect
        x1, y1 = x + self_irect.left, y + self_irect.bottom
        mouse = ui.mouse[0] - x1, ui.mouse[1] - y1
        self.pre_draw(ui, x, y)
        scissor = ui.ctx.scissor
        ui.ctx.scissor = self.srect.offset(x, y)
        inside = ui.inside
        cover = None
        if inside:
            for child in self:
                if gui6.box(mouse, child.rect):
                    cover = child
        x2 = x + self_rect.left
        x3 = x2 + gui6.YGNodeLayoutGetWidth(self.node)
        y2 = y + self_rect.bottom
        y3 = y2 + gui6.YGNodeLayoutGetHeight(self.node)
        for child in self:
            ui.inside = child is cover
            rect = child.rect.offset(x1, y1)
            ix = max(rect.left, x2) <= min(rect.right, x3)
            iy = max(rect.bottom, y2) <= min(rect.top, y3)
            if ix and iy:
                child.draw(ui, x1, y1)
        ui.ctx.scissor = scissor
        ui.inside = inside and None is cover
        self.post_draw(ui, x, y)
        ui.inside = inside

#detach_context_menu = namedtuple('detach_context_menu', [])

class ContextMenuSheet(gui6.Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with gui6.NodeContextManager(self):
            gui6.position_type(gui6.Absolute)
            gui6.width_percent(100.0)
            gui6.height_percent(100.0)

    def post_draw(self, ui, x, y):
        if ui.inside and ui.buttons > 0:
            ui.queue(self.root.close_context_menu, self)

class ContextMenu(gui6.Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with gui6.NodeContextManager(self):
            gui6.position_type(gui6.Absolute)
            gui6.padding(gui6.All, 2.0)

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x, y)
        gui6.fill(ui, (0.6,0.6,0.6, 1.0), rect)

class Border(gui6.Node):
    def __init__(self, *args, color=(0,0,0,1), **kwargs):
        super().__init__(*args, **kwargs)
        self.color = color

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x,y)
        gui6.trace(ui, self.color, rect)
        
class Fill(gui6.Node):
    def __init__(self, *args, color=(0,0,0,1), **kwargs):
        super().__init__(*args, **kwargs)
        self.color = color

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x,y)
        gui6.fill(ui, self.color, rect)

class Button(gui6.Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    clicked : gui6.Signal

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x,y)
        if ui.inside:
            ui.hotitem = self
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = self
                gui6.trace(ui, (0.5,0.5,0.5,1), rect)
                gui6.fill(ui, (0.5,0.2,0.2,0.2), rect)
            else:
                gui6.trace(ui, (0.5,0.5,0.5,1), rect)
                gui6.fill(ui, (0,0,0,0.2), rect)
        else:
            gui6.trace(ui, (0,0,0,1), rect)
        if ui.buttons == 0 and ui.hotitem == self and ui.activeitem == self:
            ui.queue(self.clicked.emit)

def measure_label(noderef, width, widthMode, height, heightMode):
    font_height, text = gui6.YGNodeGetContext(noderef)
    font = gui6.ui.get().mem(FontEngine, int(font_height))
    width = font.measure(text)
    height = font.ascent + font.descent
    return gui6.YGSize(width, height)

class Label(gui6.Node):
    def __init__(self, *args, text="", color=(0,0,0,1), font_height=16, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = text
        self.color = color
        self.font_height = font_height
        gui6.YGNodeSetContext(self.node, (self.font_height, self._text))
        gui6.YGNodeSetMeasureFunc(self.node, measure_label)
        gui6.YGNodeSetNodeType(self.node, gui6.Text)

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text
        gui6.YGNodeSetContext(self.node, (self.font_height, self._text))

    def __del__(self):
        gui6.YGNodeSetContext(self.node, None)
        super().__del__()

    def update(self):
        gui6.YGNodeSetContext(self.node, (self.font_height, self.text))
        gui6.YGNodeMarkDirty(self.node)

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x,y)
        font = ui.mem(FontEngine, int(self.font_height))
        font.prepare(self.color)
        font.text(self.text, rect.left, rect.bottom + font.descent)
        font.finish()

class TextBox(Label):
    changed : gui6.Signal

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x,y)
        if ui.focus == self:
            pos, tail, text = ui.focusstate
            if self.text != self._text:
                pos, tail, text = len(self._text), len(self._text), self._text
        else:
            pos, tail, text = 0, 0, self._text

        if ui.inside:
            ui.hotitem = self
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = self
                ui.focus = self
                pos = tail = position_to_cursor(ui, rect, ui.mouse[0], text, self.font_height)
                ui.focusstate = pos, tail, text
        if ui.activeitem == self and ui.buttons & 1 > 0 and ui.focus == self:
            pos = position_to_cursor(ui, rect, ui.mouse[0], text, self.font_height)
            ui.focusstate = pos, tail, text
        if ui.focus == self:
            for action in ui.keyboard:
                match action:
                    case gui6.KeyDown(sym, repeat, modifiers):
                        if sym == sdl2.SDLK_BACKSPACE and pos != tail:
                            pos, tail, text = delete_selection((pos, tail, text))
                        elif sym == sdl2.SDLK_BACKSPACE and pos > 0:
                            text = text[:pos - 1] + text[pos:]
                            tail = pos = pos - 1
                        elif sym == sdl2.SDLK_DELETE and pos != tail:
                            pos, tail, text = delete_selection((pos, tail, text))
                        elif sym == sdl2.SDLK_DELETE and pos < len(text):
                            text = text[:pos] + text[pos + 1:]
                        elif sym == sdl2.SDLK_LEFT and pos > 0:
                            pos = pos - 1
                            if not (modifiers & sdl2.KMOD_SHIFT):
                                tail = pos
                        elif sym == sdl2.SDLK_RIGHT and pos < len(text):
                            pos = pos + 1
                            if not (modifiers & sdl2.KMOD_SHIFT):
                                tail = pos
                        elif sym == sdl2.SDLK_HOME:
                            pos = 0
                            if not (modifiers & sdl2.KMOD_SHIFT):
                                tail = pos
                        elif sym == sdl2.SDLK_END:
                            pos = len(text)
                            if not (modifiers & sdl2.KMOD_SHIFT):
                                tail = pos
                    case gui6.KeyUp(sym, modifiers):
                        pass
                    case gui6.KeyText(inp):
                        pos,_,text = delete_selection((pos, tail, text))
                        text = text[:pos] + inp + text[pos:]
                        pos += len(inp)
                        tail = pos
            ui.focusstate = pos, tail, text
            if ui.focusstate[2] != self.text:
                self.text = ui.focusstate[2]
                ui.queue(self.changed.emit, self.text)

        font = ui.mem(FontEngine, int(self.font_height))
        def text_position(pos):
            return font.measure(text[:pos])
        _x,_y,w,h = rect
        scissor = ui.ctx.scissor
        ui.ctx.scissor = rect

        if ui.focus == self and pos != tail:
            start = min(pos, tail)
            end = max(pos, tail)
            gui6.fill(ui, (0.6, 0.8, 1.0, 0.5), (
                _x + text_position(start), _y,
                text_position(end) - text_position(start), h))
        super().pre_draw(ui, x, y)
        if ui.focus == self and pos == tail:
            cursor_x = text_position(pos)
            gui6.fill(ui, self.color,
                (_x + cursor_x, _y + font.descent * 0.5, 1, h - font.descent))
        ui.ctx.scissor = scissor

def delete_selection(buffer):
    pos,tail,text = buffer
    if pos != tail:
        start = min(pos, tail)
        end   = max(pos, tail)
        text  = text[:start] + text[end:]
        return start, start, text
    else:
        return pos, tail, text

def position_to_cursor(ui, this, x, text, height):
    font = ui.mem(FontEngine, int(height))
    x_offset = this.left
    for i, char in enumerate(text):
        char_width = font.measure(char)
        if x_offset + char_width / 2 >= x:
            return i
        x_offset += char_width
    return len(text)

def line_draw_setup(ui):
   program = ui.mem(gui6.plain_line_program)
   data = np.full(4, 0.0, dtype=np.float32)
   buffer = ui.ctx.buffer(data)
   vao = ui.ctx.vertex_array(program, buffer, 'point')
   return program, vao, buffer, data

def clock(t, rect):
    ui = gui5.context.get()
    gui5.trace((0,0,0,1), rect)
    gui5.circle_fill((0.9, 0.9, 0.9,1.0), rect)
    gui5.circle_stroke((0,0,0,1), rect)
    radius = min(rect[2], rect[3]) * 0.5
    x = rect[0] + rect[2]*0.5
    y = rect[1] + rect[3]*0.5
    angle = (t % 60) / 60 * math.pi * 2

    program, vao, buffer, data = ui.mem(line_draw_setup)
    program['scroll'] = ui.scroll_x, ui.scroll_y
    program['size'] = ui.widget.width, ui.widget.height
    program['color'] = 1,0,0,1
    data[0] = x
    data[1] = y
    data[2] = x + math.sin(angle) * radius
    data[3] = y - math.cos(angle) * radius
    buffer.write(data)
    vao.render(mode=ui.ctx.LINES)

#def triangle_wave(time):
#    t = time % (2 * math.pi)
#    if t < math.pi:
#        return 2 * (t / math.pi) - 1
#    else:
#        return 1 - 2 * ((t - math.pi) / math.pi)
#
#@gui4.composable
#def scrollinglabel(text, time, width, height=20, edge_pad=5):
#    @gui4.drawing
#    def textfill(ui, _, this):
#        font = ui.mem(FontEngine, int(height))
#        x,y,w,h = this.layout.rect
#        text_width = font.measure(text)
#        u = triangle_wave(time) * 0.5 + 0.5
#        scroll_x = - max(0, text_width - w + edge_pad*2) * u
#        ui.ctx.scissor = x - ui.scroll_x,y - ui.scroll_y,w,h
#        font.prepare((0,0,0,1))
#        font.text(text, x+edge_pad+scroll_x, y + font.descent)
#        font.finish()
#        ui.ctx.scissor = None
#    @gui4.layout
#    def _size_(cn, this):
#        font = cn.ui.mem(FontEngine, int(height))
#        cn(cn[this].width == width)
#        cn(cn[this].height == font.ascent + font.descent)
#
#@gui4.composable
#def button(text, height=20, disabled=False):
#    @gui4.logic()
#    def button_logic(ui, ident, layout):
#        if ui.inside:
#            ui.hotitem = ident
#            if ui.activeitem is None and ui.buttons > 0:
#                ui.activeitem = ident
#        if ui.buttons == 0 and ui.hotitem == ident and ui.activeitem == ident:
#            return True
#        return False
#
#    @gui4.drawing
#    def buttonfill(ui, ident, this):
#        x,y,w,h = this.layout.rect
#        pressed = (ui.activeitem == ident)
#
#        if pressed and not disabled:
#            vao, program = ui.mem(gui4.rectangle_filler)
#            program['scroll'] = ui.scroll_x, ui.scroll_y
#            program['size'] = ui.widget.width, ui.widget.height
#            program['rect'] = x,y,w,h
#            program['color'] = 0,0,0,1
#            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#        else:
#            vao, program = ui.mem(gui4.rectangle_filler)
#            program['scroll'] = ui.scroll_x, ui.scroll_y
#            program['size'] = ui.widget.width, ui.widget.height
#            program['rect'] = x,y,w,h
#            program['color'] = 1,1,1,1
#            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#
#        if not disabled:
#            a = 1*int(pressed)
#            color = a,a,a,1
#        else:
#            color = 0.5,0.5,0.5,1
#
#        vao, program = ui.mem(gui4.rectangle_stroker)
#        program['scroll'] = ui.scroll_x, ui.scroll_y
#        program['size'] = ui.widget.width, ui.widget.height
#        program['rect'] = x,y,w,h
#        program['color'] = color
#        vao.render(vertices=8, mode=ui.ctx.LINES)
#
#        font = ui.mem(FontEngine, int(height))
#        font.prepare(color)
#        font.text(text, x, y + font.descent)
#        font.finish()
#    @gui4.layout
#    def _size_(cn, this):
#        font = cn.ui.mem(FontEngine, int(height))
#        width = font.measure(text)
#        cn(cn[this].width == width)
#        cn(cn[this].height == font.ascent + font.descent)
#
#def oscilloscope_drawer(ui, sample_count):
#    program = ui.mem(gui4.plain_line_program)
#    data = np.full(sample_count*2, 0.0, dtype=np.float32)
#    buffer = ui.ctx.buffer(data)
#    vao = ui.ctx.vertex_array(program, buffer, 'point')
#    return program, vao, buffer, data
#
#@gui4.composable
#def oscilloscope(out0, out1, width=500, height=150):
#    @gui4.drawing
#    def oscillos(ui, _, this):
#        x,y,w,h = this.layout.rect
#        r  = h / 2
#        program, vao, buffer, data = ui.mem(oscilloscope_drawer, len(out0))
#        program['scroll'] = ui.scroll_x, ui.scroll_y
#        program['size'] = ui.widget.width, ui.widget.height
#        program['color'] = 1,0,0,0.5
#        xs = np.linspace(0, 1, len(out0)) * w + x
#        ys = out0 * r + y + r
#        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
#        vao.render(mode=ui.ctx.LINE_STRIP)
#        program['color'] = 0,1,0,0.5
#        xs = np.linspace(0, 1, len(out1)) * w + x
#        ys = out1 * r + y + r
#        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
#        vao.render(mode=ui.ctx.LINE_STRIP)
#    @gui4.layout
#    def _size_(cn, this):
#        cn(cn[this].width == width)
#        cn(cn[this].height == height)
#
#def get_volume(out):
#    r0 = math.sqrt(sum(out*out) / len(out))
#    return r0
#
#def decay_function(decay = 0.60):
#    def _decay_(old, new):
#        return max(new, old*decay)
#    return _decay_
#
#@gui4.composable
#def vu_meter(out0, out1, width=20, height=90):
#    gui4.trace((0,0,0,1))
#    gui4.fill((0,0,0,1))
#    @gui4.layout
#    def _size_(cn, this):
#        cn(cn[this].width == width)
#        cn(cn[this].height == height)
#
#    def to_scaler(v):
#        if v > 0:
#            dbfs = 20 * math.log10(v)
#            return min(1.0, max(0.0, 1 - (dbfs / -96)))
#        else:
#            return 0.0
#    vol0 = get_volume(out0)
#    vol1 = get_volume(out1)
#    this = gui4.state[1](
#        vol0 = 0.0, vol1 = 0.0, clip0 = False, clip1 = False)
#    this.vol0 = decay_function()(this.vol0, vol0)
#    this.vol1 = decay_function()(this.vol1, vol1)
#    this.clip0 = this.clip0 or max(abs(out0)) > 1.0
#    this.clip1 = this.clip1 or max(abs(out1)) > 1.0
#
#    @gui4.drawing
#    def _draw_(ui, _, that):
#        x,y,w,h = that.layout.rect
#        vao, program = ui.mem(gui4.rectangle_filler)
#        program['scroll'] = ui.scroll_x, ui.scroll_y
#        program['size'] = ui.widget.width, ui.widget.height
#        program['color'] = 0,1,0,1
#        h0 = to_scaler(this.vol0) * (h - 10)
#        program['rect'] = x+1, y, w // 2 - 2, h0
#        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#        h1 = to_scaler(this.vol1) * (h - 10)
#        program['rect'] = x+w//2+1, y, 8, h1
#        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#        program['color'] = 1,0,0,1
#        if this.clip0:
#            program['rect'] = x, y + h - 10, w//2, 10
#            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#        if this.clip1:
#            program['rect'] = x+w//2, y + h - 10, w//2, 10
#            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
#
#    @gui4.logic()
#    def button_logic(ui, ident, layout):
#        if ui.inside:
#            ui.hotitem = ident
#            if ui.activeitem is None and ui.buttons > 0:
#                ui.activeitem = ident
#        if ui.buttons == 0 and ui.hotitem == ident and ui.activeitem == ident:
#            this.clip0 = False
#            this.clip1 = False
#            return True
#        return False
#
#@gui4.composable
#def virtual_keyboard(editor):
#    virtual_midi = [
#        [ 49, 50, 51, 52, 53, 54, 55, 56, 57, 48],
#        [113,119,101,114,116,121,117,105,111,112],
#        [ 97,115,100,102,103,104,106,107,108,246],
#        [122,120, 99,118, 98,110,109, 44, 46, 45],
#    ]
#
#    virtual_map = {cel: 57 + i + j*2
#        for i, row in enumerate(virtual_midi)
#        for j, cel in enumerate(row)}
#
#    @gui4.logic()
#    def vkeyb_logic(ui, ident, layout):
#        if ui.inside:
#            ui.hotitem = ident
#            if ui.activeitem is None and ui.buttons > 0:
#                ui.activeitem = ident
#                ui.focus = ident
#        if ui.focus == ident:
#            editor.audio_output.lock()
#            for action in ui.keyboard:
#                if isinstance(action, (gui4.Down,gui4.Up)):
#                    k = virtual_map.get(action.sym, None)
#                    if k is None:
#                        continue
#                    if isinstance(action, gui4.Down) and action.repeat == 0:
#                        m = On(k, 1.0)
#                        editor.fire_midi_keyboard(ui, m)
#                    elif isinstance(action, gui4.Up):
#                        m = Off(k)
#                        editor.fire_midi_keyboard(ui, m)
#            editor.audio_output.unlock()
#    gui4.trace((0,0,0,1))
#    @gui4.layout
#    def _size_(cn, this):
#        cn(cn[this].width == 100)
#        cn(cn[this].height == 50)
#
#@gui4.composable
#def clavier_visualizer(editor):
#    gui4.trace((0,0,0,1))
#    this = gui4.state[1](hold = Map(), release = set())
#    @gui4.logic()
#    def _clavier_logic_(ui, ident, layout):
#        now = editor.time
#        for e in ui.clavier:
#            if isinstance(e, On):
#                this.hold = this.hold.set(e.note, now)
#            if isinstance(e, Off):
#                try:
#                    this.release.add((this.hold[e.note], now, e.note))
#                    this.hold = this.hold.delete(e.note)
#                except KeyError:
#                    pass
#        for s,e,n in list(this.release):
#            if e < now-15:
#                this.release.discard((s,e,n))
#
#    @gui4.drawing
#    def track_display(ui, _, that):
#        x,y,w,h = that.layout.rect
#        now = editor.time
#        begin = now - 15
#        for s,e,n in this.release:
#            a = max(s - begin, 0)
#            b = max(e - begin, 0)
#            program, vao, buffer, data = ui.mem(line_draw_setup)
#            program['scroll'] = ui.scroll_x, ui.scroll_y
#            program['size'] = ui.widget.width, ui.widget.height
#            program['color'] = 1,0,0,1
#            data[0] = x + a/15*w
#            data[1] = y + n
#            data[2] = x + b/15*w
#            data[3] = y + n
#            buffer.write(data)
#            vao.render(mode=ui.ctx.LINES)
#
#        hold = this.hold
#        for note, s in hold.items():
#            a = max(s - begin, 0)
#            program, vao, buffer, data = ui.mem(line_draw_setup)
#            program['scroll'] = ui.scroll_x, ui.scroll_y
#            program['size'] = ui.widget.width, ui.widget.height
#            program['color'] = 0,0,1,0.5
#            data[0] = x + a/15*w
#            data[1] = y + note
#            data[2] = x + w
#            data[3] = y + note
#            buffer.write(data)
#            vao.render(mode=ui.ctx.LINES)
#
#    @gui4.layout
#    def _size_(cn, this):
#        cn(cn[this].width == 100)
#        cn(cn[this].height == 128)
