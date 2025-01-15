from reaction import *
from visual import gui3, gui4
from visual.font import FontEngine
from aural.box import On, Off
from immutables import Map
import sdl2
import math
import numpy as np
import moderngl

def line_draw_setup(ui):
   program = ui.mem(gui3.plain_line_program)
   data = np.full(4, 0.0, dtype=np.float32)
   buffer = ui.ctx.buffer(data)
   vao = ui.ctx.vertex_array(program, buffer, 'point')
   return program, vao, buffer, data

@gui4.composable
def clock(t, width=50, height=50):
    gui4.trace((0,0,0,1))
    gui4.circle_fill((0.9, 0.9, 0.9,1.0))
    gui4.circle_stroke((0,0,0,1))
    @gui4.drawing
    def clock_hand(ui, _, this):
        radius = min(this.layout.width, this.layout.height) * 0.5
        x = this.layout.hcenter
        y = this.layout.vcenter
        angle = (t % 60) / 60 * math.pi * 2

        program, vao, buffer, data = ui.mem(line_draw_setup)
        program['size'] = ui.widget.width, ui.widget.height
        program['color'] = 1,0,0,1
        data[0] = x
        data[1] = y
        data[2] = x + math.sin(angle) * radius
        data[3] = y - math.cos(angle) * radius
        buffer.write(data)
        vao.render(mode=ui.ctx.LINES)
    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == width)
        cn(cn[this].height == height)

@gui4.composable
def colorbox(color, width=15, height=15):
    gui4.fill(color)
    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == width)
        cn(cn[this].height == height)

@gui4.composable
def label(text, height=20, color=(0,0,0,1)):
    @gui4.drawing
    def textfill(ui, _, this):
        x,y,w,h = this.layout.rect
        font = ui.mem(FontEngine, int(height))
        font.prepare(color)
        font.text(text, x, y + font.descent)
        font.finish()
    @gui4.layout
    def _size_(cn, this):
        font = cn.ui.mem(FontEngine, int(height))
        width = font.measure(text)
        cn(cn[this].width == width)
        cn(cn[this].height == font.ascent + font.descent)

def triangle_wave(time):
    t = time % (2 * math.pi)
    if t < math.pi:
        return 2 * (t / math.pi) - 1
    else:
        return 1 - 2 * ((t - math.pi) / math.pi)

@gui4.composable
def scrollinglabel(text, time, width, height=20, edge_pad=5):
    @gui4.drawing
    def textfill(ui, _, this):
        font = ui.mem(FontEngine, int(height))
        x,y,w,h = this.layout.rect
        text_width = font.measure(text)
        u = triangle_wave(time) * 0.5 + 0.5
        scroll_x = - max(0, text_width - w + edge_pad*2) * u
        ui.ctx.scissor = x,y,w,h
        font.prepare((0,0,0,1))
        font.text(text, x+edge_pad+scroll_x, y + font.descent)
        font.finish()
        ui.ctx.scissor = None
    @gui4.layout
    def _size_(cn, this):
        font = cn.ui.mem(FontEngine, int(height))
        cn(cn[this].width == width)
        cn(cn[this].height == font.ascent + font.descent)

def initbuf(text):
    return len(text), len(text), text

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
    x_offset = this.left + 5
    for i, char in enumerate(text):
        char_width = font.measure(char)
        if x_offset + char_width / 2 >= x:
            return i
        x_offset += char_width
    return len(text)

@gui4.composable
def textbox(model, width=200, height=20):
    @gui4.drawing
    def textfill(ui, ident, this):
        if ui.focus == ident:
            pos, tail, text = ui.focusstate
        else:
            pos, tail, text = 0, 0, model.value
        text = model.value

        font = ui.mem(FontEngine, int(height))
        def text_position(pos):
            return 5 + font.measure(text[:pos])
        x,y,w,h = this.layout.rect
        ui.ctx.scissor = x,y,w,h
        if ui.focus == ident and pos != tail:
            start = min(pos, tail)
            end = max(pos, tail)
            vao, program = ui.mem(gui3.rectangle_filler)
            program['size'] = ui.widget.width, ui.widget.height
            program['rect'] = (
                x + text_position(start), y,
                text_position(end) - text_position(start), h)
            program['color'] = 0.6, 0.8, 1.0, 0.5
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        font.prepare((0,0,0,1))
        font.text(text, x+5, y + font.descent)
        font.finish()
        if ui.focus == ident and pos == tail:
            cursor_x = text_position(pos)
            vao, program = ui.mem(gui3.rectangle_filler)
            program['size'] = ui.widget.width, ui.widget.height
            program['rect'] = (x + cursor_x, y + font.descent * 0.5, 1, h - font.descent)
            program['color'] = 0,0,0,1
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        ui.ctx.scissor = None
    @gui4.layout
    def _size_(cn, this):
        font = cn.ui.mem(FontEngine, int(height))
        cn(cn[this].width == width)
        cn(cn[this].height == font.ascent + font.descent)
    @gui4.logic()
    def textbox_logic(ui, ident, layout):
        if ui.focus == ident and ui.focusstate[2] != model.value:
            pos = len(model.value)
            ui.focusstate = pos, pos, model.value
        if ui.inside:
            ui.hotitem = ident
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = ident
                ui.focus = ident
                pos = position_to_cursor(ui, layout, ui.mouse[0], model.value, height)
                ui.focusstate = pos, pos, model.value
        if ui.activeitem == ident and ui.buttons & 1 > 0 and ui.focus == ident:
            pos = position_to_cursor(ui, layout, ui.mouse[0], model.value, height)
            ui.focusstate = pos, ui.focusstate[1], ui.focusstate[2]
        if ui.focus == ident:
            pos, tail, text = ui.focusstate
            for action in ui.keyboard:
                match action:
                    case gui4.Down(sym, repeat, modifiers):
                        if sym == sdl2.SDLK_BACKSPACE and pos != tail:
                            pos, tail, text = delete_selection((pos, tail, text))
                        elif sym == sdl2.SDLK_BACKSPACE and pos > 0:
                            text = text[:pos - 1] + text[pos:]
                            tail = pos = pos - 1
                            control.modified.send(text)
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
                    case gui4.Up(sym, modifiers):
                        pass
                    case gui4.Text(inp):
                        pos,_,text = delete_selection((pos, tail, text))
                        text = text[:pos] + inp + text[pos:]
                        pos += len(inp)
                        tail = pos
            ui.focusstate = pos, tail, text
            if ui.focusstate[2] != model.value:
                model.value = ui.focusstate[2]
                return True
        return False

@gui4.composable
def button(text, height=20, disabled=False):
    @gui4.logic()
    def button_logic(ui, ident, layout):
        if ui.inside:
            ui.hotitem = ident
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = ident
        if ui.buttons == 0 and ui.hotitem == ident and ui.activeitem == ident:
            return True
        return False

    @gui4.drawing
    def buttonfill(ui, ident, this):
        x,y,w,h = this.layout.rect
        pressed = (ui.activeitem == ident)

        if pressed and not disabled:
            vao, program = ui.mem(gui3.rectangle_filler)
            program['size'] = ui.widget.width, ui.widget.height
            program['rect'] = x,y,w,h
            program['color'] = 0,0,0,1
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        else:
            vao, program = ui.mem(gui3.rectangle_filler)
            program['size'] = ui.widget.width, ui.widget.height
            program['rect'] = x,y,w,h
            program['color'] = 1,1,1,1
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)

        if not disabled:
            a = 1*int(pressed)
            color = a,a,a,1
        else:
            color = 0.5,0.5,0.5,1

        vao, program = ui.mem(gui3.rectangle_stroker)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = x,y,w,h
        program['color'] = color
        vao.render(vertices=8, mode=ui.ctx.LINES)

        font = ui.mem(FontEngine, int(height))
        font.prepare(color)
        font.text(text, x, y + font.descent)
        font.finish()
    @gui4.layout
    def _size_(cn, this):
        font = cn.ui.mem(FontEngine, int(height))
        width = font.measure(text)
        cn(cn[this].width == width)
        cn(cn[this].height == font.ascent + font.descent)

def oscilloscope_drawer(ui, sample_count):
    program = ui.mem(gui3.plain_line_program)
    data = np.full(sample_count*2, 0.0, dtype=np.float32)
    buffer = ui.ctx.buffer(data)
    vao = ui.ctx.vertex_array(program, buffer, 'point')
    return program, vao, buffer, data

@gui4.composable
def oscilloscope(out0, out1, width=500, height=150):
    @gui4.drawing
    def oscillos(ui, _, this):
        x,y,w,h = this.layout.rect
        r  = h / 2
        program, vao, buffer, data = ui.mem(oscilloscope_drawer, len(out0))
        program['size'] = ui.widget.width, ui.widget.height
        program['color'] = 1,0,0,0.5
        xs = np.linspace(0, 1, len(out0)) * w + x
        ys = out0 * r + y + r
        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
        vao.render(mode=ui.ctx.LINE_STRIP)
        program['color'] = 0,1,0,0.5
        xs = np.linspace(0, 1, len(out1)) * w + x
        ys = out1 * r + y + r
        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
        vao.render(mode=ui.ctx.LINE_STRIP)
    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == width)
        cn(cn[this].height == height)

def get_volume(out):
    r0 = math.sqrt(sum(out*out) / len(out))
    return r0

def decay_function(decay = 0.60):
    def _decay_(old, new):
        return max(new, old*decay)
    return _decay_

@gui4.composable
def vu_meter(out0, out1, width=20, height=90):
    gui4.trace((0,0,0,1))
    gui4.fill((0,0,0,1))
    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == width)
        cn(cn[this].height == height)

    def to_scaler(v):
        if v > 0:
            dbfs = 20 * math.log10(v)
            return min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            return 0.0
    vol0 = get_volume(out0)
    vol1 = get_volume(out1)
    this = gui4.state[1](
        vol0 = 0.0, vol1 = 0.0, clip0 = False, clip1 = False)
    this.vol0 = decay_function()(this.vol0, vol0)
    this.vol1 = decay_function()(this.vol1, vol1)
    this.clip0 = this.clip0 or max(abs(out0)) > 1.0
    this.clip1 = this.clip1 or max(abs(out1)) > 1.0

    @gui4.drawing
    def _draw_(ui, _, that):
        x,y,w,h = that.layout.rect
        vao, program = ui.mem(gui3.rectangle_filler)
        program['size'] = ui.widget.width, ui.widget.height
        program['color'] = 0,1,0,1
        h0 = to_scaler(this.vol0) * (h - 10)
        program['rect'] = x+1, y, w // 2 - 2, h0
        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        h1 = to_scaler(this.vol1) * (h - 10)
        program['rect'] = x+w//2+1, y, 8, h1
        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        program['color'] = 1,0,0,1
        if this.clip0:
            program['rect'] = x, y + h - 10, w//2, 10
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        if this.clip1:
            program['rect'] = x+w//2, y + h - 10, w//2, 10
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)

    @gui4.logic()
    def button_logic(ui, ident, layout):
        if ui.inside:
            ui.hotitem = ident
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = ident
        if ui.buttons == 0 and ui.hotitem == ident and ui.activeitem == ident:
            this.clip0 = False
            this.clip1 = False
            return True
        return False

@gui4.composable
def virtual_keyboard(editor):
    virtual_midi = [
        [ 49, 50, 51, 52, 53, 54, 55, 56, 57, 48],
        [113,119,101,114,116,121,117,105,111,112],
        [ 97,115,100,102,103,104,106,107,108,246],
        [122,120, 99,118, 98,110,109, 44, 46, 45],
    ]

    virtual_map = {cel: 57 + i + j*2
        for i, row in enumerate(virtual_midi)
        for j, cel in enumerate(row)}

    @gui4.logic()
    def vkeyb_logic(ui, ident, layout):
        if ui.inside:
            ui.hotitem = ident
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = ident
                ui.focus = ident
        if ui.focus == ident:
            editor.audio_output.lock()
            for action in ui.keyboard:
                if isinstance(action, (gui4.Down,gui4.Up)):
                    k = virtual_map.get(action.sym, None)
                    if k is None:
                        continue
                    if isinstance(action, gui4.Down) and action.repeat == 0:
                        m = On(k, 1.0)
                        editor.fire_midi_keyboard(ui, m)
                    elif isinstance(action, gui4.Up):
                        m = Off(k)
                        editor.fire_midi_keyboard(ui, m)
            editor.audio_output.unlock()
    gui4.trace((0,0,0,1))
    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == 100)
        cn(cn[this].height == 50)

@gui4.composable
def clavier_visualizer(editor):
    gui4.trace((0,0,0,1))
    this = gui4.state[1](hold = Map(), release = set())
    @gui4.logic()
    def _clavier_logic_(ui, ident, layout):
        now = editor.time
        for e in ui.clavier:
            if isinstance(e, On):
                this.hold = this.hold.set(e.note, now)
            if isinstance(e, Off):
                try:
                    this.release.add((this.hold[e.note], now, e.note))
                    this.hold = this.hold.delete(e.note)
                except KeyError:
                    pass
        for s,e,n in list(this.release):
            if e < now-15:
                this.release.discard((s,e,n))

    @gui4.drawing
    def track_display(ui, _, that):
        x,y,w,h = that.layout.rect
        now = editor.time
        begin = now - 15
        for s,e,n in this.release:
            a = max(s - begin, 0)
            b = max(e - begin, 0)
            program, vao, buffer, data = ui.mem(line_draw_setup)
            program['size'] = ui.widget.width, ui.widget.height
            program['color'] = 1,0,0,1
            data[0] = x + a/15*w
            data[1] = y + n
            data[2] = x + b/15*w
            data[3] = y + n
            buffer.write(data)
            vao.render(mode=ui.ctx.LINES)

        hold = this.hold
        for note, s in hold.items():
            a = max(s - begin, 0)
            program, vao, buffer, data = ui.mem(line_draw_setup)
            program['size'] = ui.widget.width, ui.widget.height
            program['color'] = 0,0,1,0.5
            data[0] = x + a/15*w
            data[1] = y + note
            data[2] = x + w
            data[3] = y + note
            buffer.write(data)
            vao.render(mode=ui.ctx.LINES)

    @gui4.layout
    def _size_(cn, this):
        cn(cn[this].width == 100)
        cn(cn[this].height == 128)
