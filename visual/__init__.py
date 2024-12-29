import sdl2.ext

class Widget:
    def __init__(self, title, width, height, mk_payload, *payload_args):
        self.width = width
        self.height = height
        self.window = sdl2.ext.Window(title, (width, height))
        self.uid = sdl2.SDL_GetWindowID(self.window.window)
        self.exposed = True
        self.payload = mk_payload(self, *payload_args)
        self.window.show()

def process_widgets(widgets, root):
    running = True
    events = sdl2.ext.get_events()
    for event in events:
        if event.type == sdl2.SDL_QUIT:
            running = False
            break
        elif event.type == sdl2.SDL_WINDOWEVENT_EXPOSED:
            widget = widgets[event.window.windowID]
            widget.exposed = True
        elif event.type == sdl2.SDL_MOUSEMOTION:
            widget = widgets[event.motion.windowID]
            widget.payload.mouse_motion(event.motion.x, event.motion.y)
        elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
            widget = widgets[event.button.windowID]
            widget.payload.mouse_button_down(event.button.x, event.button.y, event.button.button)
        elif event.type == sdl2.SDL_MOUSEBUTTONUP:
            if event.button.windowID == 0:
                _widgets = widgets.values()
            else:
                _widgets = [widgets[event.button.windowID]]
            for widget in _widgets:
                widget.payload.mouse_button_up(event.button.x, event.button.y, event.button.button)
        elif event.type == sdl2.SDL_TEXTINPUT:
            widget = widgets[event.text.windowID]
            text = event.text.text.decode('utf-8')
            widget.payload.text_input(text)
        elif event.type == sdl2.SDL_KEYDOWN:
            widget = widgets[event.key.windowID]
            widget.payload.key_down(event.key.keysym.sym, bool(event.key.repeat), event.key.keysym.mod)
        elif event.type == sdl2.SDL_KEYUP:
            widget = widgets[event.key.windowID]
            widget.payload.key_up(event.key.keysym.sym, event.key.keysym.mod)
        elif event.type == sdl2.SDL_WINDOWEVENT:
            widget = widgets.get(event.window.windowID)
            if event.window.event == sdl2.video.SDL_WINDOWEVENT_CLOSE:
                if widget.payload.closing():
                    if widget is root:
                        for widget in list(widgets.values()):
                            widget.payload.close()
                            widget.window.close()
                            widgets.pop(widget.uid)
                        running = False
                    else:
                        widget.payload.close()
                        widget.window.close()
                        widgets.pop(widget.uid)

    for widget in widgets.values():
        widget.payload.update()
        if widget.exposed:
            widget.exposed = False
            widget.payload.draw()
        widget.window.refresh()

    sdl2.SDL_Delay(60)

    return running

class DummyPayload:
    def __init__(self, widget):
        pass

    def draw(self):
        pass

    def update(self):
        pass

    def mouse_motion(self, x, y):
        pass

    def mouse_button_down(self, x, y, button):
        pass

    def mouse_button_up(self, x, y, button):
        pass

    def text_input(self, text):
        pass

    def key_down(self, sym, repeat, modifiers):
        pass

    def key_up(self, sym, modifiers):
        pass

    def closing(self):
        return True

    def close(self):
        pass
