import gui
import sdl2
from contextlib import contextmanager

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

e_dialog_leave = object()

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
