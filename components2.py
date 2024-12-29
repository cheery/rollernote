from reaction import *
from visual import gui2
import math

def colorbox(color, width, height):
    @gui2.drawing(color)
    def _draw_(ui, this, color):
        ui.ctx.set_source_rgba(*color)
        this.shape.trace(ui.ctx)
        ui.ctx.stroke()
        this.shape.trace(ui.ctx)
        ui.ctx.fill()
    return gui2.Frame([_draw_], gui2.DynamicLayout(width, height))

def label(text):
    height = 20
    @gui2.drawing(text)
    def _draw_(ui, this, text):
        bb = this.shape
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.set_font_size(20)
        xt = ui.ctx.text_extents(text)
        ui.ctx.move_to(bb.x + 5, bb.y + bb.height / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
    return gui2.Frame([_draw_], gui2.DynamicLayout(height=height, flexible_width=True))

def triangle_wave(time):
    t = time % (2 * math.pi)
    if t < math.pi:
        return 2 * (t / math.pi) - 1
    else:
        return 1 - 2 * ((t - math.pi) / math.pi)

def scrollinglabel(text, time, width):
    height = 20
    @gui2.drawing(text, time, in_clip=True)
    def _draw_(ui, this, text, time):
        bb = this.shape
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.set_font_size(20)
        xt = ui.ctx.text_extents(text)
        u = triangle_wave(time) * 0.5 + 0.5
        scroll_x = - max(0, xt.width - width + 10) * u
        ui.ctx.move_to(bb.x + 5 + scroll_x, bb.y + bb.height / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
    return gui2.Frame([_draw_], gui2.DynamicLayout(width=width, height=height))

def initbuf(text):
    return len(text), len(text), text

class TextBox:
    def __init__(self, initial, set_text=None):
        self.mutation = Event()
        if set_text:
            mutor = Merge(self.mutation, MapE(lambda text: lambda _: initbuf(text), set_text))
        else:
            mutor = self.mutation
        def _updater_(x,f):
            return f(x)
        self.buffer  = Memory(initbuf(initial), _updater_, mutor)
        self.text    = Compute(lambda x: x[2], [self.buffer])
        self.changes = Changes(self.text)

def delete_selection(buffer):
    start = min(buffer[0], buffer[1])
    end   = max(buffer[0], buffer[1])
    text  = buffer[2][:start] + buffer[2][end:]
    return start, start, text

def position_to_cursor(ui, this, x, text):
    ui.ctx.set_font_size(20)
    x_offset = this.shape.x + 5
    for i, char in enumerate(text):
        char_width = ui.ctx.text_extents(char)[4]
        if x_offset + char_width / 2 >= x:
            return i
        x_offset += char_width
    return len(text)

def textbox(control):
    chars    = Event()
    keyboard = Event()
    motion   = Event()
    buttons  = [Event(), Event(), Event()]
    width  = 200
    height = 20

    caret_event = Event()
    caret = Hold(0, caret_event)

    snap  = FilterE(lambda x: x, buttons[0])
    drag  = Hold(False, buttons[0])

    def left_button_click(_, pos):
        def mutor(buffer):
            return pos, pos, buffer[2]
        return mutor
    mutations = Snapshot(left_button_click, snap, caret)

    def dragging_motion(_, pos):
        def mutor(buffer):
            return pos, buffer[1], buffer[2]
        return mutor
    dragging  = FilterE(lambda x: x, Snapshot(lambda _, y: y, motion, drag))
    mutations = Merge(mutations, Snapshot(dragging_motion, dragging, caret))

    def char_stream(ch):
        def mutor(buffer):
            pos, tail, text = buffer
            if pos != tail:
                pos, tail, text = delete_selection((pos, tail, text))
            text = text[:pos] + ch + text[pos:]
            pos  = pos + len(ch)
            return pos, pos, text
        return mutor
    mutations = Merge(mutations, MapE(char_stream, chars))

    def key_stream(action):
        def mutor(buffer):
            pos, tail, text = buffer
            key = action.sym
            modifiers = action.modifiers
            if key == sdl2.SDLK_BACKSPACE and pos != tail:
                pos, tail, text = delete_selection((pos, tail, text))
            elif key == sdl2.SDLK_BACKSPACE and pos > 0:
                text = text[:pos - 1] + text[pos:]
                tail = pos = pos - 1
            elif key == sdl2.SDLK_DELETE and pos != tail:
                pos, tail, text = delete_selection((pos, tail, text))
            elif key == sdl2.SDLK_DELETE and pos < len(text):
                text = text[:pos] + text[pos + 1:]
            elif key == sdl2.SDLK_LEFT and pos > 0:
                pos = pos - 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail = pos
            elif key == sdl2.SDLK_RIGHT and pos < len(text):
                pos = pos + 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail = pos
            elif key == sdl2.SDLK_HOME:
                pos = 0
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail = pos
            elif key == sdl2.SDLK_END:
                pos = len(text)
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail = pos
            return pos, tail, text
        if isinstance(action, gui2.Down):
            return mutor
        else:
            return lambda x: x
    mutations = Merge(mutations, MapE(key_stream, keyboard))

    @gui2.logic(Snapshot(lambda xy, text: (xy, text), motion, control.text))
    def _caret_logic_(ui, this, xyts):
        for (x,y),text in xyts:
            ui.engine.send(caret_event, position_to_cursor(ui, this, x, text))

    @gui2.logic(mutations)
    def _buffer_logic_(ui, this, muts):
        for mut in muts:
            ui.engine.send(control.mutation, mut)

    @gui2.drawing(control.buffer)
    def _draw_(ui, this, buffer):
        pos, tail, text = buffer
        def text_position(pos):
            return 5 + ui.ctx.text_extents(text[:pos])[4]
        bb = this.shape
        ui.ctx.set_source_rgba(1, 1, 1, 1)
        bb.trace(ui.ctx)
        ui.ctx.fill()
        ui.ctx.set_source_rgba(0, 0, 0, 1)
        bb.trace(ui.ctx)
        ui.ctx.stroke()
        ui.ctx.set_font_size(20)
        xt = ui.ctx.text_extents(text)
        if pos != tail:
            start = min(pos, tail)
            end = max(pos, tail)
            ui.ctx.set_source_rgba(0.6, 0.8, 1, 0.5)  # Light blue highlight
            ui.ctx.rectangle(bb.x + text_position(start),
                             bb.y + bb.height / 2 + xt.y_bearing,
                             text_position(end) - text_position(start),
                             20)
            ui.ctx.fill()
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.move_to(bb.x + 5, bb.y + bb.height / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
        if ui.keyboard_focus == this and pos == tail:
            cursor_x = text_position(pos)
            ui.ctx.move_to(bb.x + cursor_x, bb.y + bb.height / 2 - xt.y_bearing / 2)
            ui.ctx.line_to(bb.x + cursor_x, bb.y + bb.height / 2 + xt.y_bearing / 2)
            ui.ctx.stroke()
    return gui2.Frame([_caret_logic_, _buffer_logic_, _draw_], gui2.DynamicLayout(width=width, height=height, flexible_width=True),
               chars=chars,
               keyboard=keyboard,
               motion=motion,
               buttons=buttons)

def button(ui, text, left, middle, right):
    buttons = [left, middle, right]
    b0 = Hold(False, buttons[0])
    b1 = Hold(False, buttons[1])
    b2 = Hold(False, buttons[2])
    pressed = Compute(lambda x,y,z: x or y or z, [b0,b1,b2])
    disabled = False
    ui.ctx.set_font_size(20)
    xt = ui.ctx.text_extents(text.value) # TODO: Everything should be changing!!!
    width = xt.width + 20
    height = xt.height + 10
    @gui2.drawing(pressed, text)
    def _draw_(ui, this, pressed, text):
        bb = this.shape
        if pressed and not disabled:
            ui.ctx.set_source_rgba(0, 0, 0, 1)
            bb.trace(ui.ctx)
            ui.ctx.fill()
        else:
            ui.ctx.set_source_rgba(1, 1, 1, 1)
            bb.trace(ui.ctx)
            ui.ctx.fill()
        ui.ctx.set_font_size(20)
        if not disabled:
            a = 1*int(pressed)
            ui.ctx.set_source_rgba(a,a,a,1)
        else:
            ui.ctx.set_source_rgba(0.5, 0.5, 0.5, 1)
        xt = ui.ctx.text_extents(text)
        ui.ctx.move_to(
            bb.x + bb.width / 2 - xt.width / 2,
            bb.y + bb.height / 2 - xt.y_bearing / 2)
        ui.ctx.show_text(text)
        bb.trace(ui.ctx)
        ui.ctx.stroke()
    return gui2.Frame([_draw_], gui2.DynamicLayout(width, height), buttons=buttons)

def oscilloscope(out0, out1, width=500, height=150):
    @gui2.drawing(out0, out1)
    def oscillos(ui, this, left, right):
        bb = this.shape
        r  = bb.height / 2
        ui.ctx.set_source_rgba(1,0,0,0.5)
        ui.ctx.move_to(bb.x, bb.y + r - r*left[0])
        for i in range(1, len(left)):
            t = i / len(left)
            ui.ctx.line_to(bb.x + t*bb.width, bb.y + r - r*left[i])
        ui.ctx.stroke()
        ui.ctx.set_source_rgba(0,1,0,0.5)
        ui.ctx.move_to(bb.x, bb.y + r - r*right[0])
        for i in range(1, len(right)):
            t = i / len(right)
            ui.ctx.line_to(bb.x + t*bb.width, bb.y + r - r*right[i])
        ui.ctx.stroke()
    return gui2.Frame([ oscillos ], gui2.DynamicLayout(width=width, height=height))

def get_volume(out):
    r0 = math.sqrt(sum(out*out) / len(out))
    return r0

def get_clip(out, reset=False):
    return max(int(max(abs(out)) > 1.0), 2*int(reset))

def decay_function(decay = 0.60):
    def _decay_(old, new):
        return max(new, old*decay)
    return _decay_

def vu_meter(out0, out1, width=20, height=90):
    def to_scaler(v):
        if v > 0:
            dbfs = 20 * math.log10(v)
            return min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            return 0.0
    buttons = [Event(), Event(), Event()]

    volume0 = Accum(0.0, decay_function(), Compute(get_volume, [out0]))
    volume1 = Accum(0.0, decay_function(), Compute(get_volume, [out1]))
    clip0   = Compute(get_clip, [out0, Hold(False, buttons[0])])
    clip1   = Compute(get_clip, [out1, Hold(False, buttons[0])])
    clipping0 = Accum(0, lambda x,y: max(x,y)%2, clip0)
    clipping1 = Accum(0, lambda x,y: max(x,y)%2, clip0)

    @gui2.drawing(volume0, volume1, clipping0, clipping1)
    def _draw_(ui, this, vol0, vol1, clip0, clip1):
        bb = this.shape
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        bb.trace(ctx)
        ctx.fill()
        bb.trace(ctx)
        ctx.stroke()
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        h0 = to_scaler(vol0) * (bb.height - 10)
        ctx.rectangle(bb.x+1, bb.y+bb.height - h0,
                      bb.width // 2 - 2, h0)
        ctx.fill()
        h1 = to_scaler(vol1) * (bb.height - 10)
        ctx.rectangle(bb.x+bb.width//2+1, bb.y+bb.height - h1, 8, h1)
        ctx.fill()
        ctx.set_source_rgba(1.0, 0.0, 0.0, 1.0)
        if clip0:
            ctx.rectangle(bb.x, bb.y, bb.width//2, 10)
        if clip1:
            ctx.rectangle(bb.x+bb.width//2, bb.y, bb.width//2, 10)
        ctx.fill()

    return gui2.Frame([_draw_], gui2.DynamicLayout(width, height), buttons=buttons)

