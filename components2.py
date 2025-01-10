from reaction import *
from visual import gui3
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

def clock(t, width=50, height=50):

    @gui3.drawing(t)
    def clock_hand(ui, this, t):
        radius = min(this.width.value(), this.height.value())/2
        x = this.hcenter.value()
        y = this.vcenter.value()
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

    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        gui3.circle_fill((0.9, 0.9, 0.9,1.0)),
        gui3.circle_stroke((0,0,0,1)),
        clock_hand,
        gui3.Width(width),
        gui3.Height(height),
    ])

def colorbox(color, width=5, height=5):
    return gui3.Frame([
        gui3.fill(color),
        gui3.Width(width),
        gui3.Height(height),
    ])

from PIL import Image, ImageDraw, ImageFont
from visual import atlas

class FontEngine:
    def __init__(self, ui, size):
        ui.mem(gui3.common_interface)
        self.ui = ui
        self.font = ImageFont.truetype('OpenSans-Regular.ttf', size=size)
        self.image = Image.new("L", (1024, 1024), color=0)
        self.draw = ImageDraw.Draw(self.image)
        self.atlas = atlas.AtlasAllocator(1024, 1024)
        self.mapping = dict()
        self.upload = False
        self.texture = ui.ctx.texture(self.image.size, 1)
        self.sampler = ui.ctx.sampler(texture=self.texture)
        self.sampler.filter = ui.ctx.NEAREST, ui.ctx.NEAREST

        self.ascent, self.descent = self.font.getmetrics()
        self.program = ui.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 xy;
                in vec4 xywh;
                out vec4 _xywh;
                void main() {
                    gl_Position = vec4(xy, 0.0, 1.0);
                    _xywh = xywh;
                }
            """,
            geometry_shader="""
                #version 330 core
                #include "common_ui"
                layout (points) in;
                layout (triangle_strip, max_vertices=4) out;
                in vec4 _xywh[];
                out vec2 uv;
                uniform vec2 uv_size;
                void main() {
                    vec2 position = gl_in[0].gl_Position.xy;
                    vec2 u0 = _xywh[0].xy / uv_size;
                    vec2 wh = _xywh[0].zw;
                    vec2 u1 = u0 + wh / uv_size;

                    gl_Position = vec4(pixel_to_screen(position + vec2(0, wh.y)), 0, 1);
                    uv = vec2(u0.x, u1.y);
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position + wh), 0, 1); 
                    uv = u1;
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position), 0, 1);
                    uv = u0;
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position + vec2(wh.x, 0)), 0, 1);
                    uv = vec2(u1.x, u0.y);
                    EmitVertex();
                    EndPrimitive();
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D sample;
                uniform vec4 color;
                in vec2 uv;
                out vec4 rgba;
                void main() {
                    rgba = color * vec4(1,1,1, texture(sample, uv).x);
                }
            """)
        self.vdata = np.full(6*4096, 0.0, dtype=np.float32)
        self.vcount = 0
        self.vbo = ui.ctx.buffer(self.vdata)
        self.vao = ui.ctx.vertex_array(self.program, self.vbo, 'xy', 'xywh')

    def inmap(self, ch):
        if ch not in self.mapping:
            (width, baseline), (offset_x, offset_y) = self.font.font.getsize(ch)
            mask = self.font.getmask(ch)
            bbox = mask.getbbox()
            if bbox is None:
                rect = None
                offset_y = 0
            else:
                mask = Image.frombytes(mask.mode, mask.size, bytes(mask))
                mask = mask.transpose(Image.FLIP_TOP_BOTTOM)
                ow, oh = mask.size
                ox, oy = self.atlas.alloc(ow, oh)
                self.draw.bitmap((ox, oy), mask, fill=255)
                self.upload = True
                rect = ox, oy, ow, oh
                offset_y = self.ascent - oh - offset_y
            self.mapping[ch] = (offset_x, offset_y), rect, width
        return self.mapping[ch]

    def measure(self, string):
        x = 0
        for ch in string:
            (offset_x, offset_y), rect, width = self.inmap(ch)
            x += width
        return x

    def prepare(self, color):
        self.program['size'] = self.ui.widget.width, self.ui.widget.height
        self.program['uv_size'] = 1024, 1024
        self.program['color'] = color
        self.program['sample'] = 0
        self.sampler.use(0)

    def text(self, string, x, y):
        for ch in string:
            (offset_x, offset_y), rect, width = self.inmap(ch)
            if rect is not None:
                ix = self.vcount*6
                self.vdata[ix+0] = x + offset_x
                self.vdata[ix+1] = y + offset_y
                self.vdata[ix+2:ix+6] = rect
                self.vcount += 1
                if self.vcount >= 4096:
                    self.finish()
            x += width

    def finish(self):
        if self.upload:
            self.texture.write(self.image.tobytes())
            self.upload = False
        self.vbo.write(self.vdata)
        self.vao.render(vertices=self.vcount, mode=self.ui.ctx.POINTS)
        self.vcount = 0

def label(text, height=20, color=(0,0,0,1)):
    @gui3.drawing(text, height, color)
    def textfill(ui, this, text, height, color):
        font = ui.mem(FontEngine, int(height))
        x,y,w,h = this.computed_box
        font.prepare(color)
        font.text(text, x+5, y + font.descent)
        font.finish()
    def f0(ui, this, solver, text, height):
        solver.addEditVariable(this.width, 'strong')
        solver.addEditVariable(this.height, 'strong')
    def f1(ui, this, solver, text, height):
        font = ui.mem(FontEngine, int(height))
        width = font.measure(text)
        solver.suggestValue(this.width, width + 10)
        solver.suggestValue(this.height, font.ascent + font.descent)
    return gui3.Frame([
        textfill,
        gui3.CustomLayout(f0, f1, text, height),
    ])

def triangle_wave(time):
    t = time % (2 * math.pi)
    if t < math.pi:
        return 2 * (t / math.pi) - 1
    else:
        return 1 - 2 * ((t - math.pi) / math.pi)

def scrollinglabel(text, time, width, height=20):
    @gui3.drawing(text, time)
    def textfill(ui, this, text, time):
        font = ui.mem(FontEngine, int(height))
        x,y,w,h = this.computed_box
        text_width = font.measure(text)
        u = triangle_wave(time) * 0.5 + 0.5
        scroll_x = - max(0, text_width - w + 10) * u
        ui.ctx.scissor = x,y,w,h
        font.prepare((0,0,0,1))
        font.text(text, x+5+scroll_x, y + font.descent)
        font.finish()
        ui.ctx.scissor = None
    def f0(ui, this, solver, text, height):
        solver.addEditVariable(this.height, 'strong')
    def f1(ui, this, solver, text, height):
        font = ui.mem(FontEngine, int(height))
        width = font.measure(text)
        solver.suggestValue(this.height, font.ascent + font.descent)
    return gui3.Frame([
        textfill,
        gui3.Width(width),
        gui3.CustomLayout(f0, f1, text, height),
    ])

# ----------------------------------------------

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
    x_offset = this.left.value() + 5
    for i, char in enumerate(text):
        char_width = font.measure(char)
        if x_offset + char_width / 2 >= x:
            return i
        x_offset += char_width
    return len(text)

class TextControl:
    def __init__(self, ui, initial):
        self.ui = ui
        self.modified = Source(ui.engine)
        self.text     = Hold(initial, self.modified)
        self.buffer   = initbuf(initial)

    def set_text(self, text):
        self.buffer = initbuf(text)
        self.modified.send(text)

def textbox(control, width=200, height=20):
    mouse = gui3.MouseControl(control.ui)
    keyboard = gui3.KeyboardControl(control.ui)
    position = Hold((0,0), mouse.motion)
    dragging = Hold(False, mouse.left.pressed)
    @gui3.logic(mouse.left.down, position)
    def mouse_click(ui, this, down, xy):
        if down:
            _, _, text = control.buffer
            pos = position_to_cursor(ui, this, xy[0], text, height)
            control.buffer = pos, pos, text
    @gui3.logic(dragging, position)
    def mouse_drag(ui, this, pressed, xy):
        if pressed:
            _, tail, text = control.buffer
            pos = position_to_cursor(ui, this, xy[0], text, height)
            control.buffer = pos, tail, text
    @gui3.logic(keyboard.stream)
    def keyboard_stream(ui, this, stream):
        if stream is None:
            return
        for action in stream.value:
            match action:
                case gui3.Down(sym, repeat, modifiers):
                    pos, tail, text = control.buffer
                    modifiers = action.modifiers
                    if sym == sdl2.SDLK_BACKSPACE and pos != tail:
                        pos, tail, text = delete_selection((pos, tail, text))
                        control.modified.send(text)
                    elif sym == sdl2.SDLK_BACKSPACE and pos > 0:
                        text = text[:pos - 1] + text[pos:]
                        tail = pos = pos - 1
                        control.modified.send(text)
                    elif sym == sdl2.SDLK_DELETE and pos != tail:
                        pos, tail, text = delete_selection((pos, tail, text))
                        control.modified.send(text)
                    elif sym == sdl2.SDLK_DELETE and pos < len(text):
                        text = text[:pos] + text[pos + 1:]
                        control.modified.send(text)
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
                    control.buffer = pos,tail,text
                case gui3.Up(sym, modifiers):
                    pass
                case gui3.Text(inp):
                    pos,_,text = delete_selection(control.buffer)
                    text = text[:pos] + inp + text[pos:]
                    pos += len(inp)
                    control.buffer = pos,pos,text
                    control.modified.send(text)

    @gui3.drawing(Hold(False, keyboard.focus))
    def textfill(ui, this, focus):
        pos, tail, text = control.buffer
        font = ui.mem(FontEngine, int(height))
        def text_position(pos):
            return 5 + font.measure(text[:pos])
        x,y,w,h = this.computed_box
        ui.ctx.scissor = x,y,w,h
        if focus and pos != tail:
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
        if focus and pos == tail:
            cursor_x = text_position(pos)
            vao, program = ui.mem(gui3.rectangle_filler)
            program['size'] = ui.widget.width, ui.widget.height
            program['rect'] = (x + cursor_x, y + font.descent * 0.5, 1, h - font.descent)
            program['color'] = 0,0,0,1
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        ui.ctx.scissor = None
    def f0(ui, this, solver, text, height):
        solver.addEditVariable(this.height, 'strong')
    def f1(ui, this, solver, text, height):
        font = ui.mem(FontEngine, int(height))
        width = font.measure(text)
        solver.suggestValue(this.height, font.ascent + font.descent)
    return gui3.Frame([
        gui3.fill((1,1,1,1)),
        gui3.trace((0,0,0,1)),
        mouse_click,
        mouse_drag,
        keyboard_stream,
        textfill,
        gui3.Width(width),
        gui3.CustomLayout(f0, f1, control.text, height),
    ], keyboard=keyboard, mouse=mouse)

def button(ui, text, height=20, mouse=None, disabled=False):
    mouse = mouse or gui3.MouseControl(ui)
    left = Hold(False, mouse.left.pressed)
    middle = Hold(False, mouse.middle.pressed)
    right = Hold(False, mouse.right.pressed)
    pressed = compute(left, middle, right)(lambda x,y,z: x or y or z)
    @compute(pressed, promote(disabled))
    def color(pressed, disabled):
        if not disabled:
            a = 1*int(pressed)
            return a,a,a,1
        else:
            return 0.5,0.5,0.5,1

    @gui3.drawing(pressed, disabled, color)
    def buttonfill(ui, this, pressed, disabled, color):
        x,y,w,h = this.computed_box
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
        vao, program = ui.mem(gui3.rectangle_stroker)
        program['size'] = ui.widget.width, ui.widget.height
        program['rect'] = x,y,w,h
        program['color'] = color
        vao.render(vertices=8, mode=ui.ctx.LINES)
    return gui3.Frame([
        buttonfill,
    ] + label(text, height, color).contents, mouse=mouse)

def oscilloscope_drawer(ui, sample_count):
    program = ui.mem(gui3.plain_line_program)
    data = np.full(sample_count*2, 0.0, dtype=np.float32)
    buffer = ui.ctx.buffer(data)
    vao = ui.ctx.vertex_array(program, buffer, 'point')
    return program, vao, buffer, data

def oscilloscope(out0, out1, width=500, height=150):
    @gui3.drawing(out0, out1)
    def oscillos(ui, this, left, right):
        x,y,w,h = this.computed_box
        r  = h / 2
        program, vao, buffer, data = ui.mem(oscilloscope_drawer, len(left))
        program['size'] = ui.widget.width, ui.widget.height
        program['color'] = 1,0,0,0.5
        xs = np.linspace(0, 1, len(left)) * w + x
        ys = left * r + y + r
        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
        vao.render(mode=ui.ctx.LINE_STRIP)
        program['color'] = 0,1,0,0.5
        xs = np.linspace(0, 1, len(right)) * w + x
        ys = right * r + y + r
        buffer.write(np.dstack([xs, ys]).flatten().astype(np.float32))
        vao.render(mode=ui.ctx.LINE_STRIP)
    return gui3.Frame([
        oscillos,
        gui3.Width(width),
        gui3.Height(height),
    ])

def get_volume(out):
    r0 = math.sqrt(sum(out*out) / len(out))
    return r0

def get_clip(out, reset=False):
    return max(int(max(abs(out)) > 1.0), 2*int(reset))

def decay_function(decay = 0.60):
    def _decay_(old, new):
        return max(new, old*decay)
    return _decay_

def vu_meter(ui, out0, out1, width=20, height=90):
    def to_scaler(v):
        if v > 0:
            dbfs = 20 * math.log10(v)
            return min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            return 0.0
    mouse = gui3.MouseControl(ui)
    volume0 = Accum(0.0, decay_function(), [Compute(get_volume, [out0])])
    volume1 = Accum(0.0, decay_function(), [Compute(get_volume, [out1])])

    clip0   = Compute(get_clip, [out0, Hold(False, mouse.left.pressed)])
    clip1   = Compute(get_clip, [out1, Hold(False, mouse.left.pressed)])
    clipping0 = Accum(0, lambda x,y: max(x,y)%2, [clip0])
    clipping1 = Accum(0, lambda x,y: max(x,y)%2, [clip0])

    @gui3.drawing(volume0, volume1, clipping0, clipping1)
    def _draw_(ui, this, vol0, vol1, clip0, clip1):
        x,y,w,h = this.computed_box
        vao, program = ui.mem(gui3.rectangle_filler)
        program['size'] = ui.widget.width, ui.widget.height
        program['color'] = 0,1,0,1
        h0 = to_scaler(vol0) * (h - 10)
        program['rect'] = x+1, y, w // 2 - 2, h0
        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        h1 = to_scaler(vol1) * (h - 10)
        program['rect'] = x+w//2+1, y, 8, h1
        vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        program['color'] = 1,0,0,1
        if clip0:
            program['rect'] = x, y + h - 10, w//2, 10
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
        if clip1:
            program['rect'] = x+w//2, y + h - 10, w//2, 10
            vao.render(vertices=4, mode=ui.ctx.TRIANGLE_STRIP)
    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        gui3.fill((0,0,0,1)),
        _draw_, gui3.Width(width), gui3.Height(height)], mouse=mouse)

def virtual_keyboard(editor, ui):
    virtual_midi = [
        [ 49, 50, 51, 52, 53, 54, 55, 56, 57, 48],
        [113,119,101,114,116,121,117,105,111,112],
        [ 97,115,100,102,103,104,106,107,108,246],
        [122,120, 99,118, 98,110,109, 44, 46, 45],
    ]

    virtual_map = {cel: 57 + i + j*2
        for i, row in enumerate(virtual_midi)
        for j, cel in enumerate(row)}

    keyboard = gui3.KeyboardControl(ui)

    @gui3.logic(keyboard.stream)
    def _midi_logic_(ui, this, actions):
        if actions:
            editor.audio_output.lock()
            for action in actions.value:
                if isinstance(action, (gui3.Down,gui3.Up)):
                    k = virtual_map.get(action.sym, None)
                    if k is None:
                        continue
                    if isinstance(action, gui3.Down) and action.repeat == 0:
                        m = On(k, 1.0)
                        editor.fire_midi_keyboard(ui, m)
                    elif isinstance(action, gui3.Up):
                        m = Off(k)
                        editor.fire_midi_keyboard(ui, m)
            editor.audio_output.unlock()
    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        _midi_logic_,
        gui3.Width(100),
        gui3.Height(50),
    ], keyboard=keyboard)

def clavier_visualizer(clavier, now):
    def hold_down(holdr, esn):
        hold,release = holdr
        es,now = esn
        for e in es:
            if isinstance(e, On):
                hold = hold.set(e.note, now)
            if isinstance(e, Off):
                try:
                    release.add((hold[e.note], now, e.note))
                    hold = hold.delete(e.note)
                except KeyError:
                    pass
        return hold,release
    wth_time = snapshot(clavier, now)(lambda es,t: (es,t))
    holdr = Memory((Map(),set()), hold_down, wth_time)
    @compute(holdr, now)
    def t15(holdr, now):
        _,release = holdr
        for s,e,n in list(release):
            if e < now-15:
                release.discard((s,e,n))
        return release

    @gui3.drawing(holdr, t15, now)
    def track_display(ui, this, holdr, t15, now):
        x,y,w,h = this.computed_box
        begin = now - 15
        for s,e,n in t15:
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

        hold,_ = holdr
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

    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        track_display,
        gui3.Width(100),
        gui3.Height(128),
    ])
