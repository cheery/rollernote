"""
    Commands record actions made for document.
"""
import gui

class DemoCommand:
    def __init__(self):
        self.name = "demo command added during init"
    def do(self, document):
        print('done')
    def undo(self, document):
        print('undone')

class History:
    def __init__(self, document):
        self.document = document
        self.undo_stack = []
        self.redo_stack = []

    def do(self, command):
        self.redo_stack.clear()
        command.do(self.document)
        self.undo_stack.append(command)

    def undo(self):
        command = self.undo_stack.pop()
        command.undo(self.document)
        self.redo_stack.append(command)

    def redo(self):
        command = self.redo_stack.pop()
        command.do(self.document)
        self.undo_stack.append(command)
         
def history_toolbar(history, ctx, hit):
    ctx.select_font_face('FreeSerif')
    ctx.set_font_size(24)
    box = gui.Box(100, 10, 32, 32)
    hit.append(box)
    if len(history.undo_stack) > 0:
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        def f(x, y, button):
            history.undo()
            return True
        box.on_button_down = f
    else:
        ctx.set_source_rgba(0.7, 0.7, 0.7, 1.0)
    ctx.rectangle(100, 10, 32, 32)
    ctx.stroke()
    symbol = chr(0x21B6)
    xt = ctx.text_extents(symbol)
    ctx.move_to(100+15-xt.width/2-xt.x_bearing, 32)
    ctx.show_text(symbol)
    box = gui.Box(133, 10, 32, 32)
    hit.append(box)
    if len(history.redo_stack) > 0:
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        def f(x, y, button):
            history.redo()
            return True
        box.on_button_down = f
    else:
        ctx.set_source_rgba(0.7, 0.7, 0.7, 1.0)
    ctx.rectangle(133, 10, 32, 32)
    ctx.stroke()
    symbol = chr(0x21B7)
    xt = ctx.text_extents(symbol)
    ctx.move_to(133+16-xt.width/2-xt.x_bearing, 32)
    ctx.show_text(symbol)
    ctx.set_font_size(12)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
    if len(history.undo_stack) > 0:
        ctx.move_to(166+10, 22)
        ctx.show_text(f"undo: {history.undo_stack[-1].name}")
    if len(history.redo_stack) > 0:
        ctx.move_to(166+10, 36)
        ctx.show_text(f"redo: {history.redo_stack[-1].name}")
