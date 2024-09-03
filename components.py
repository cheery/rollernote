import gui
import sdl2
from contextlib import contextmanager

@gui.composable
def colorbox(color, *args, **kwargs):
    gui.layout(gui.DynamicLayout(*args, **kwargs))
    @gui.drawing
    def _draw_(ui, comp):
        ui.ctx.set_source_rgba(*color)
        comp.shape.trace(ui.ctx)
        ui.ctx.stroke()
        comp.shape.trace(ui.ctx)
        ui.ctx.fill()

@gui.composable
def label2(text, font_size=20):
    _ui = gui.ui.get()
    _ui.ctx.set_font_size(font_size)
    extents = _ui.ctx.text_extents(text)
    gui.layout(gui.DynamicLayout(extents.width, extents.height))
    @gui.drawing
    def _draw_(ui, comp):
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.set_font_size(font_size)
        ui.ctx.move_to(comp.shape.x, comp.shape.y + comp.shape.height)
        ui.ctx.show_text(text)

@gui.composable
def button2(text, font_size=20, disabled=False, min_width=0, flexible_width=False, flexible_height=False):
    _ui = gui.ui.get()
    _ui.ctx.set_font_size(font_size)
    extents = _ui.ctx.text_extents(text)
    gui.layout(gui.DynamicLayout(max(min_width, extents.width + 20), extents.height + 10, flexible_width, flexible_height))
    this = gui.lazybundle(pressed = False)

    @gui.drawing
    def _draw_(ui, comp):
        bb = comp.shape
        ctx = ui.ctx
        if this.pressed and not disabled:
            ctx.set_source_rgba(0, 0, 0, 1)
            comp.shape.trace(ui.ctx)
            ctx.fill()
        else:
            ctx.set_source_rgba(1, 1, 1, 1)
            comp.shape.trace(ui.ctx)
            ctx.fill()
        ctx.set_font_size(font_size)
        if not disabled:
            ctx.set_source_rgba(1*int(this.pressed), 1*int(this.pressed), 1*int(this.pressed), 1)
        else:
            ctx.set_source_rgba(0.5, 0.5, 0.5, 1)
        xt = ctx.text_extents(text)
        ctx.move_to(
            bb.x + bb.width / 2 - xt.width / 2,
            bb.y + bb.height / 2 - xt.y_bearing / 2)
        ctx.show_text(text)
        comp.shape.trace(ui.ctx)
        ctx.stroke()
    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        this.pressed = True
    @gui.listen(gui.e_button_up)
    def _up_(x, y, button):
        this.pressed = False

@gui.composable
def textbox2(text, change_text, font_size=20, min_width=0, flexible_width=False, flexible_height=False):
    this = gui.lazybundle(
        pos = len(text),
        tail = len(text),
        buf = text,
        dragging = False,
    )

    _ui = gui.ui.get()
    _ui.ctx.set_font_size(font_size)
    extents = _ui.ctx.text_extents(this.buf)
    gui.layout(gui.DynamicLayout(max(min_width, extents.width + 20), font_size + 10, flexible_width, flexible_height))

    comp = gui.current_composition.get()
    def text_position(pos):
        ctx = gui.ui.get().ctx
        ctx.set_font_size(font_size)
        return 5 + ctx.text_extents(this.buf[:pos])[4]

    def position_to_cursor(x):
        # Estimate the position based on the mouse x-coordinate
        ctx = gui.ui.get().ctx
        ctx.set_font_size(font_size)
        x_offset = comp.shape.x + 5
        for i, char in enumerate(this.buf):
            char_width = ctx.text_extents(char)[4]
            if x_offset + char_width / 2 >= x:
                return i
            x_offset += char_width
        return len(this.buf)

    def delete_selection():
        start = min(this.pos, this.tail)
        end = max(this.pos, this.tail)
        this.buf = this.buf[:start] + this.buf[end:]
        this.pos = start
        this.tail = this.pos

    @gui.drawing
    def _draw_(ui, comp):
        bb = comp.shape
        ctx = ui.ctx
        ctx.set_source_rgba(1, 1, 1, 1)
        comp.shape.trace(ctx)
        ctx.fill()
        ctx.set_source_rgba(0, 0, 0, 1)
        comp.shape.trace(ctx)
        ctx.stroke()
        xt = ctx.text_extents(this.buf)
        if this.pos != this.tail:
            start = min(this.pos, this.tail)
            end = max(this.pos, this.tail)
            ctx.set_source_rgba(0.6, 0.8, 1, 0.5)  # Light blue highlight
            ctx.rectangle(bb.x + text_position(start),
                          bb.y + bb.height / 2 + xt.y_bearing,
                          text_position(end) - text_position(start),
                          font_size)
            ctx.fill()
        ctx.set_source_rgb(0, 0, 0)  # Black text
        ctx.set_font_size(font_size)
        ctx.move_to(bb.x + 5, bb.y + bb.height / 2 - xt.y_bearing / 2)
        ctx.show_text(this.buf)

        if ui.focus == comp.key and this.pos == this.tail:
            cursor_x = text_position(this.pos)
            ctx.move_to(bb.x + cursor_x, bb.y + 5)
            ctx.line_to(bb.x + cursor_x, bb.y + font_size + 5)
            ctx.stroke()

    @gui.listen(gui.e_key_down)
    def _key_down_(key, repeat, modifiers):
        if key == sdl2.SDLK_BACKSPACE:
            if this.pos != this.tail:
                delete_selection()
            elif this.pos > 0:
                this.buf = this.buf[:this.pos - 1] + this.buf[this.pos:]
                this.pos -= 1
                this.tail = this.pos
            change_text(this.buf)
        elif key == sdl2.SDLK_DELETE:
            if this.pos != this.tail:
                delete_selection()
            elif this.pos < len(this.buf):
                this.buf = this.buf[:this.pos] + this.buf[this.pos + 1:]
            change_text(this.buf)
        elif key == sdl2.SDLK_LEFT:
            if this.pos > 0:
                this.pos -= 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    this.tail = this.pos
        elif key == sdl2.SDLK_RIGHT:
            if this.pos < len(this.buf):
                this.pos += 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    this.tail = this.pos
        elif key == sdl2.SDLK_HOME:
            this.pos = 0
            if not (modifiers & sdl2.KMOD_SHIFT):
                this.tail = this.pos
        elif key == sdl2.SDLK_END:
            this.pos = len(this.buf)
            if not (modifiers & sdl2.KMOD_SHIFT):
                this.tail = this.pos

    @gui.listen(gui.e_text)
    def _text_(inp):
        if this.pos != this.tail:
            delete_selection()
        this.buf = this.buf[:this.pos] + inp + this.buf[this.pos:]
        this.pos += len(inp)
        this.tail = this.pos
        change_text(this.buf)

    @gui.listen(gui.e_motion)
    @gui.listen(gui.e_dragging)
    def _motion_(x, y):
        if this.dragging:
            this.pos = position_to_cursor(x)

    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            this.pos = position_to_cursor(x)
            this.tail = this.pos
            this.dragging = True

    @gui.listen(gui.e_button_up)
    def mouse_button_up(x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            this.dragging = False

@gui.composable
def label(text, x, y, font_size=20):
    @gui.drawing
    def _draw_(ui, comp):
        ui.ctx.set_source_rgba(0,0,0,1)
        ui.ctx.set_font_size(font_size)
        ui.ctx.move_to(x, y)
        ui.ctx.show_text(text)

@gui.composable
def button(text, font_size=20, disabled=False):
    pressed = gui.state(False)
    @gui.drawing
    def _draw_(ui, comp):
        bb = comp.shape
        ctx = ui.ctx
        if pressed.value and not disabled:
            ctx.set_source_rgba(0, 0, 0, 1)
            comp.shape.trace(ui.ctx)
            ctx.fill()
        else:
            ctx.set_source_rgba(1, 1, 1, 1)
            comp.shape.trace(ui.ctx)
            ctx.fill()
        ctx.set_font_size(font_size)
        if not disabled:
            ctx.set_source_rgba(1*int(pressed.value), 1*int(pressed.value), 1*int(pressed.value), 1)
        else:
            ctx.set_source_rgba(0.5, 0.5, 0.5, 1)
        xt = ctx.text_extents(text)
        ctx.move_to(
            bb.x + bb.width / 2 - xt.width / 2,
            bb.y + bb.height / 2 - xt.y_bearing / 2)
        ctx.show_text(text)
        comp.shape.trace(ui.ctx)
        ctx.stroke()
    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        pressed.value = True
    @gui.listen(gui.e_button_up)
    def _up_(x, y, button):
        pressed.value = False

@gui.composable
def textbox(text, change_text, font_size=20):
    comp = gui.current_composition.get()
    pos = gui.state(len(text))
    tail = gui.state(len(text))
    buf = gui.state(text)
    dragging = gui.state(False)
    def text_position(pos):
        ctx = gui.ui.get().ctx
        ctx.set_font_size(font_size)
        return 5 + ctx.text_extents(buf.value[:pos])[4]

    def position_to_cursor(x):
        # Estimate the position based on the mouse x-coordinate
        ctx = gui.ui.get().ctx
        ctx.set_font_size(font_size)
        x_offset = comp.shape.x + 5
        for i, char in enumerate(buf.value):
            char_width = ctx.text_extents(char)[4]
            if x_offset + char_width / 2 >= x:
                return i
            x_offset += char_width
        return len(buf.value)

    def delete_selection():
        start = min(pos.value, tail.value)
        end = max(pos.value, tail.value)
        buf.value = buf.value[:start] + buf.value[end:]
        pos.value = start
        tail.value = pos.value

    @gui.drawing
    def _draw_(ui, comp):
        bb = comp.shape
        ctx = ui.ctx
        ctx.set_source_rgba(1, 1, 1, 1)
        comp.shape.trace(ctx)
        ctx.fill()
        ctx.set_source_rgba(0, 0, 0, 1)
        comp.shape.trace(ctx)
        ctx.stroke()
        xt = ctx.text_extents(buf.value)
        if pos.value != tail.value:
            start = min(pos.value, tail.value)
            end = max(pos.value, tail.value)
            ctx.set_source_rgba(0.6, 0.8, 1, 0.5)  # Light blue highlight
            ctx.rectangle(bb.x + text_position(start),
                          bb.y + bb.height / 2 + xt.y_bearing,
                          text_position(end) - text_position(start),
                          font_size)
            ctx.fill()
        ctx.set_source_rgb(0, 0, 0)  # Black text
        ctx.set_font_size(font_size)
        ctx.move_to(bb.x + 5, bb.y + bb.height / 2 - xt.y_bearing / 2)
        ctx.show_text(buf.value)

        if ui.focus == comp.key and pos.value == tail.value:
            cursor_x = text_position(pos.value)
            ctx.move_to(bb.x + cursor_x, bb.y + bb.height / 2 - xt.y_bearing / 2)
            ctx.line_to(bb.x + cursor_x, bb.y + bb.height / 2 + xt.y_bearing / 2)
            ctx.stroke()

    @gui.listen(gui.e_key_down)
    def _key_down_(key, repeat, modifiers):
        if key == sdl2.SDLK_BACKSPACE and pos.value > 0:
            if pos.value != tail.value:
                delete_selection()
            else:
                buf.value = buf.value[:pos.value - 1] + buf.value[pos.value:]
                pos.value -= 1
                tail.value = pos.value
            change_text(buf.value)
        elif key == sdl2.SDLK_DELETE and pos.value < len(buf.value):
            if pos.value != tail.value:
                delete_selection()
            else:
                buf.value = buf.value[:pos.value] + buf.value[pos.value + 1:]
            change_text(buf.value)
        elif key == sdl2.SDLK_LEFT:
            if pos.value > 0:
                pos.value -= 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail.value = pos.value
        elif key == sdl2.SDLK_RIGHT:
            if pos.value < len(buf.value):
                pos.value += 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    tail.value = pos.value
        elif key == sdl2.SDLK_HOME:
            pos.value = 0
            if not (modifiers & sdl2.KMOD_SHIFT):
                tail.value = pos.value
        elif key == sdl2.SDLK_END:
            pos.value = len(buf.value)
            if not (modifiers & sdl2.KMOD_SHIFT):
                tail.value = pos.value

    @gui.listen(gui.e_text)
    def _text_(inp):
        if pos.value != tail.value:
            delete_selection()
        buf.value = buf.value[:pos.value] + inp + buf.value[pos.value:]
        pos.value += len(inp)
        tail.value = pos.value
        change_text(buf.value)

        # Adjust the width of the dialog based on content width
        #text_width = len(self.text) * (self.font_size * 0.6) + 2 * self.padding
        #if text_width > self.width:
        #    self.width = text_width

    @gui.listen(gui.e_motion)
    @gui.listen(gui.e_dragging)
    def _motion_(x, y):
        if dragging.value:
            pos.value = position_to_cursor(x)

    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            pos.value = position_to_cursor(x)
            tail.value = pos.value
            dragging.value = True

    @gui.listen(gui.e_button_up)
    def mouse_button_up(x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            dragging.value = False

e_dialog_open = object()
e_dialog_leave = object()

def dialog2(shaded=True):
    def _decorator_(fn):
        _ui = gui.ui.get()
        comp = gui.current_composition.get()
        gui.layout(gui.StaticLayout(gui.PaddedLayout(gui.DynamicLayout(flexible_width=True, flexible_height=True),
                                                     100, 100, 100, 100)))
        gui.shape(gui.Box(0, 0, _ui.widget.width, _ui.widget.height))
        if shaded:
            @gui.drawing
            def _draw_(ui, comp):
                ui.ctx.set_source_rgba(0,0,0,0.5)
                ui.ctx.rectangle(0,0, ui.widget.width, ui.widget.height)
                ui.ctx.fill()

        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            gui.inform(e_dialog_leave, comp)

        this = gui.sub(fn, 1)
        return this
    return _decorator_

@contextmanager
def dialog(shape=None):
    _ui = gui.ui.get()
    comp = gui.current_composition.get()
    gui.shape(gui.Hit())

    @gui.drawing
    def _draw_(ui, comp):
        ui.ctx.set_source_rgba(0,0,0,0.5)
        ui.ctx.rectangle(0,0, ui.widget.width, ui.widget.height)
        ui.ctx.fill()

    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        _ui.custom_event(e_dialog_leave, comp)

    with gui.composition_frame(None, (shape,), {}, d=1) as comp:
        if shape is None:
            shape = gui.Box(100, 100, _ui.widget.width - 200, _ui.widget.height - 200)
        comp.shape = shape

        @gui.drawing
        def _draw_(ui, comp):
            ui.ctx.set_source_rgba(1,1,1,1)
            comp.shape.trace(ui.ctx)
            ui.ctx.fill()
            ui.ctx.set_source_rgba(0,0,0,1)
            comp.shape.trace(ui.ctx)
            ui.ctx.stroke()
            #ui.ctx.set_font_size(20)
            #ui.ctx.move_to(comp.shape.x, comp.shape.y+20)
            #ui.ctx.show_text(str(gui.format_key(comp.key)))
        # To catch the button down event.
        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            pass
         
        yield comp

def open_context_menu(comp, x, y, *args, **kwargs):
    def _decorator_(fn):
        gui.inform(e_dialog_open, comp, context_menu, fn, x, y, *args, **kwargs)
    return _decorator_

@gui.composable
def context_menu(fn, x, y, *args, **kwargs):
    @dialog2(shaded=False)
    def _contents_():
        gui.layout(MenuLayout(gui.ColumnLayout(flexible_width=True, flexible_height=True), x, y))
        gui.shape(gui.Box(0,0,0,0))
        @gui.drawing
        def _draw_(ui, comp):
            ui.ctx.set_source_rgba(1,1,1,1)
            comp.shape.trace(ui.ctx)
            ui.ctx.fill()
            ui.ctx.set_source_rgba(0,0,0,1)
            comp.shape.trace(ui.ctx)
            ui.ctx.stroke()
        fn(*args, **kwargs)

class MenuLayout(gui.StaticLayout):
    def __init__(self, inner, x, y, max_width=None, max_height=None):
        super().__init__(inner)
        self.x = x
        self.y = y
        self.max_width = max_width
        self.max_height = max_height

    def measure(self, children, available_width, available_height):
        widget = gui.ui.get().widget
        if self.max_width is not None:
            width = self.max_width
        else:
            width = widget.width
        if self.max_height is not None:
            height = self.max_height
        else:
            height = widget.height
        super().measure(children, width, height)

    def __call__(self, this, box, shallow=True):
        assert shallow
        widget = gui.ui.get().widget
        width = self.inner.calc_width
        height = self.inner.calc_height
        offset_x = max(0, self.x + width - widget.width)
        offset_y = max(0, self.y + height - widget.height)
        this.shape = gui.Box(self.x - offset_x, self.y - offset_y, width, height)
        super().__call__(this, this.shape)

