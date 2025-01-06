from reaction import *
from visual import gui3
from aural.box import On, Off
from immutables import Map
import sdl2
import math

def clock(t):
    @gui3.drawing(t)
    def clock_hand(ui, this, t):
        radius = min(this.width.value(), this.height.value())/2
        x = this.hcenter.value()
        y = this.vcenter.value()
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.arc(x, y, radius, 0, 2*math.pi)
        ui.ctx.stroke()
        angle = (t % 60) / 60 * math.pi * 2
        ui.ctx.set_source_rgba(1,0,0,1)
        ui.ctx.move_to(x, y)
        ui.ctx.line_to(x + math.sin(angle) * radius,
                       y - math.cos(angle) * radius)
        ui.ctx.stroke()

    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        clock_hand,
        gui3.Width(50),
        gui3.Height(50),
    ])

def colorbox(color, width=5, height=5):
    @gui3.drawing(color)
    def colorfill(ui, this, color):
        ui.ctx.set_source_rgba(*color)
        ui.ctx.rectangle(*this.computed_box)
        ui.ctx.stroke()
        ui.ctx.rectangle(*this.computed_box)
        ui.ctx.fill()
    return gui3.Frame([
        colorfill,
        gui3.Width(width),
        gui3.Height(height),
    ])

def label(text, height=20, color=(0,0,0,1)):
    @gui3.drawing(text, height, color)
    def textfill(ui, this, text, height, color):
        x,y,w,h = this.computed_box
        ui.ctx.set_source_rgba(*color)
        ui.ctx.set_font_size(height)
        xt = ui.ctx.text_extents(text)
        ui.ctx.move_to(x + 5, y + h / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
    def f0(ui, this, solver, text, height):
        solver.addEditVariable(this.width, 'strong')
    def f1(ui, this, solver, text, height):
        ui.ctx.set_font_size(height)
        xt = ui.ctx.text_extents(text)
        solver.suggestValue(this.width, xt.width + 10)
    return gui3.Frame([
        textfill,
        gui3.Height(height),
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
        x,y,w,h = this.computed_box
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.clip()
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.set_font_size(height)
        xt = ui.ctx.text_extents(text)
        u = triangle_wave(time) * 0.5 + 0.5
        scroll_x = - max(0, xt.width - width + 10) * u
        ui.ctx.move_to(x + 5 + scroll_x, y + h / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
    return gui3.Frame([
        textfill,
        gui3.Width(width),
        gui3.Height(height),
    ])

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

def position_to_cursor(ui, this, x, text):
    ui.ctx.set_font_size(20)
    x_offset = this.left.value() + 5
    for i, char in enumerate(text):
        char_width = ui.ctx.text_extents(char)[4]
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
            pos = position_to_cursor(ui, this, xy[0], text)
            control.buffer = pos, pos, text
    @gui3.logic(dragging, position)
    def mouse_drag(ui, this, pressed, xy):
        if pressed:
            _, tail, text = control.buffer
            pos = position_to_cursor(ui, this, xy[0], text)
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
        def text_position(pos):
            return 5 + ui.ctx.text_extents(text[:pos])[4]
        x,y,w,h = this.computed_box
        ui.ctx.set_source_rgba(1, 1, 1, 1)
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.fill()
        ui.ctx.set_source_rgba(0, 0, 0, 1)
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.stroke()
        ui.ctx.set_font_size(h)
        xt = ui.ctx.text_extents(text)
        if focus and pos != tail:
            start = min(pos, tail)
            end = max(pos, tail)
            ui.ctx.set_source_rgba(0.6, 0.8, 1, 0.5)  # Light blue highlight
            ui.ctx.rectangle(
                x + text_position(start), y,
                text_position(end) - text_position(start), h)
            ui.ctx.fill()
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.move_to(x + 5, y + h / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
        if focus and pos == tail:
            cursor_x = text_position(pos)
            ui.ctx.move_to(x + cursor_x, y + h / 2 - xt.y_bearing / 2)
            ui.ctx.line_to(x + cursor_x, y + h / 2 + xt.y_bearing / 2)
            ui.ctx.stroke()
    return gui3.Frame([
        mouse_click,
        mouse_drag,
        keyboard_stream,
        textfill,
        gui3.Width(width),
        gui3.Height(height),
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
        ui.ctx.set_font_size(h)
        if pressed and not disabled:
            ui.ctx.set_source_rgba(0, 0, 0, 1)
            ui.ctx.rectangle(x,y,w,h)
            ui.ctx.fill()
        else:
            ui.ctx.set_source_rgba(1, 1, 1, 1)
            ui.ctx.rectangle(x,y,w,h)
            ui.ctx.fill()
        ui.ctx.set_source_rgba(*color)
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.stroke()
    return gui3.Frame([
        buttonfill,
    ] + label(text, height, color).contents, mouse=mouse)

def oscilloscope(out0, out1, width=500, height=150):
    @gui3.drawing(out0, out1)
    def oscillos(ui, this, left, right):
        x,y,w,h = this.computed_box
        r  = h / 2
        ui.ctx.set_source_rgba(1,0,0,0.5)
        ui.ctx.move_to(x, y + r - r*left[0])
        for i in range(1, len(left)):
            t = i / len(left)
            ui.ctx.line_to(x + t*w, y + r - r*left[i])
        ui.ctx.stroke()
        ui.ctx.set_source_rgba(0,1,0,0.5)
        ui.ctx.move_to(x, y + r - r*right[0])
        for i in range(1, len(right)):
            t = i / len(right)
            ui.ctx.line_to(x + t*w, y + r - r*right[i])
        ui.ctx.stroke()
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
        ui.ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.fill()
        ui.ctx.rectangle(x,y,w,h)
        ui.ctx.stroke()
        ui.ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        h0 = to_scaler(vol0) * (h - 10)
        ui.ctx.rectangle(x+1, y+h - h0, w // 2 - 2, h0)
        ui.ctx.fill()
        h1 = to_scaler(vol1) * (h - 10)
        ui.ctx.rectangle(x+w//2+1, y+h - h1, 8, h1)
        ui.ctx.fill()
        ui.ctx.set_source_rgba(1.0, 0.0, 0.0, 1.0)
        if clip0:
            ui.ctx.rectangle(x, y, w//2, 10)
        if clip1:
            ui.ctx.rectangle(x+w//2, y, w//2, 10)
        ui.ctx.fill()
    return gui3.Frame([_draw_, gui3.Width(width), gui3.Height(height)], mouse=mouse)

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
        ui.ctx.set_source_rgba(1,0,0,1.0)
        for s,e,n in t15:
            a = max(s - begin, 0)
            b = max(e - begin, 0)
            ui.ctx.move_to(x+a/15*w, y + 127 - n)
            ui.ctx.line_to(x+b/15*w, y + 127 - n)
        ui.ctx.stroke()

        hold,_ = holdr
        for note, s in hold.items():
            a = max(s - begin, 0)
            ui.ctx.set_source_rgba(0,0,1,0.5)
            ui.ctx.move_to(x+a/15*w,   y + 127 - note)
            ui.ctx.line_to(x+w, y + 127 - note)
            ui.ctx.stroke()

    return gui3.Frame([
        gui3.trace((0,0,0,1)),
        track_display,
        gui3.Width(100),
        gui3.Height(128),
    ])
