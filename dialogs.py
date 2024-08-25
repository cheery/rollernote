import sdl2
import gui

class TextDialog(gui.Box):
    def __init__(self, ctx, text, font_size, x, y, width, height):
        gui.Box.__init__(self, x, y, width, height)
        self.ctx = ctx
        self.text = text
        self.cursor_pos = len(text)  # Start with the cursor at the end of the text
        self.cursor_tail = len(text)  # No selection initially
        self.has_focus = True
        self.font_size = font_size
        self.padding = 10
        self.dragging = False  # State to track dragging

    def draw(self):
        # Draw background
        self.ctx.set_source_rgb(1, 1, 1)  # White background
        self.ctx.rectangle(self.x, self.y, self.width, self.height)
        self.ctx.fill()

        # Draw border
        self.ctx.set_source_rgb(0, 0, 0)  # Black border
        self.ctx.set_line_width(2)
        self.ctx.rectangle(self.x, self.y, self.width, self.height)
        self.ctx.stroke()

        # Draw selection highlight
        if self.cursor_pos != self.cursor_tail:
            start = min(self.cursor_pos, self.cursor_tail)
            end = max(self.cursor_pos, self.cursor_tail)
            self.ctx.set_source_rgba(0.6, 0.8, 1, 0.5)  # Light blue highlight
            self.ctx.rectangle(self.x + self.text_position(start), self.y + self.padding,
                               self.text_position(end) - self.text_position(start),
                               self.font_size)
            self.ctx.fill()

        # Draw text
        self.ctx.set_source_rgb(0, 0, 0)  # Black text
        self.ctx.set_font_size(self.font_size)
        self.ctx.move_to(self.x + self.padding, self.y + self.padding + self.font_size)
        self.ctx.show_text(self.text)

        # Draw cursor if focused and no text is selected
        if self.has_focus and self.cursor_pos == self.cursor_tail:
            cursor_x = self.text_position(self.cursor_pos)
            self.ctx.move_to(self.x + cursor_x, self.y + self.padding)
            self.ctx.line_to(self.x + cursor_x, self.y + self.padding + self.font_size)
            self.ctx.stroke()

    def text_position(self, pos):
        self.ctx.set_font_size(self.font_size)
        return self.padding + self.ctx.text_extents(self.text[:pos])[4]

    def key_down(self, key, modifiers):
        if key == sdl2.SDLK_BACKSPACE and self.cursor_pos > 0:
            if self.cursor_pos != self.cursor_tail:
                self.delete_selection()
            else:
                self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                self.cursor_pos -= 1
                self.cursor_tail = self.cursor_pos
        elif key == sdl2.SDLK_DELETE and self.cursor_pos < len(self.text):
            if self.cursor_pos != self.cursor_tail:
                self.delete_selection()
            else:
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
        elif key == sdl2.SDLK_LEFT:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    self.cursor_tail = self.cursor_pos
        elif key == sdl2.SDLK_RIGHT:
            if self.cursor_pos < len(self.text):
                self.cursor_pos += 1
                if not (modifiers & sdl2.KMOD_SHIFT):
                    self.cursor_tail = self.cursor_pos
        elif key == sdl2.SDLK_HOME:
            self.cursor_pos = 0
            if not (modifiers & sdl2.KMOD_SHIFT):
                self.cursor_tail = self.cursor_pos
        elif key == sdl2.SDLK_END:
            self.cursor_pos = len(self.text)
            if not (modifiers & sdl2.KMOD_SHIFT):
                self.cursor_tail = self.cursor_pos
        return True

    def key_up(self, key, modifiers):
        return False

    def text_input(self, text):
        if self.cursor_pos != self.cursor_tail:
            self.delete_selection()
        self.text = self.text[:self.cursor_pos] + text + self.text[self.cursor_pos:]
        self.cursor_pos += len(text)
        self.cursor_tail = self.cursor_pos

        # Adjust the width of the dialog based on content width
        text_width = len(self.text) * (self.font_size * 0.6) + 2 * self.padding
        if text_width > self.width:
            self.width = text_width
        return True

    def mouse_motion(self, x, y):
        if self.dragging:
            # Update cursor position and tail for selection dragging
            self.cursor_pos = self.position_to_cursor(x)
            return True

    def mouse_button_down(self, x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            # Set focus and start dragging for text selection
            self.has_focus = True
            self.cursor_pos = self.position_to_cursor(x)
            self.cursor_tail = self.cursor_pos
            self.dragging = True
            return True

    def mouse_button_up(self, x, y, button):
        if button == sdl2.SDL_BUTTON_LEFT:
            self.dragging = False  # Stop dragging after mouse button is released
            return True

    def position_to_cursor(self, x):
        # Estimate the position based on the mouse x-coordinate
        cr = self.ctx
        cr.set_font_size(self.font_size)
        x_offset = self.x + self.padding
        for i, char in enumerate(self.text):
            char_width = cr.text_extents(char)[4]
            if x_offset + char_width / 2 >= x:
                return i
            x_offset += char_width
        return len(self.text)

    def delete_selection(self):
        start = min(self.cursor_pos, self.cursor_tail)
        end = max(self.cursor_pos, self.cursor_tail)
        self.text = self.text[:start] + self.text[end:]
        self.cursor_pos = start
        self.cursor_tail = self.cursor_pos

