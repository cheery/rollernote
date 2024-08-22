import sdl2.ext
import entities
import cairo_renderer
import cairo
import lv2
import audio
import commands
import gui
import math
# from fractions import Fraction
# import entities
# import resolution
# import commands

class Editor:
    def __init__(self):
        self.document = entities.load_document('document.mide.zip')
        self.history = commands.History(self.document)
        self.history.do(commands.DemoCommand())
        self.plugins = lv2.Plugins()
        #print(list(self.plugins.list_instrument_plugins()))
        self.plugin = self.plugins.plugin(self.document.instrument.plugin)
        #print([x[0] for x in self.plugin.audio_inputs])
        #print([x[0] for x in self.plugin.audio_outputs])
        #print(list(self.plugin.control_inputs.keys()))
        #print(list(self.plugin.control_outputs.keys()))
        #print(list(self.plugin.inputs.keys()))
        #print(list(self.plugin.outputs.keys()))
        self.transport = audio.Transport(self.plugins)
        if len(self.document.instrument.patch) > 0:
            self.plugin.load(self.document.instrument.patch, self.document.instrument.data)
        self.running = False
        self.time = 0.0
        self.widgets = dict()

        bpm = audio.LinearEnvelope([ (0, 80, -2),
                                     (4*3, 10, 0) ])
        assert bpm.check_positiveness()
        self.transport.live_voices.update([
            audio.LiveVoice(self.plugin, voice, bpm)
            for voice in self.document.track.voices
        ])

    def widget(self, *args):
        widget = Widget(*args)
        self.widgets[widget.uid] = widget
        return widget

    def ui(self):
        self.running = True
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_AUDIO)

        root = self.widget("rollernote", 1200, 700, MainPayload, self)

        while self.running:
            self.time = sdl2.SDL_GetTicks64() / 1000.0

            for widget in self.widgets.values():
                widget.payload.update()
                if widget.exposed:
                    widget.payload.draw()
                    widget.exposed = False
                widget.window.refresh()

            sdl2.SDL_Delay(20)

            events = sdl2.ext.get_events()
            for event in events:
                if event.type == sdl2.SDL_QUIT:
                    self.running = False
                    break
                elif event.type == sdl2.SDL_WINDOWEVENT_EXPOSED:
                    widget = self.widgets[event.window.windowID]
                    widget.exposed = True
                elif event.type == sdl2.SDL_MOUSEMOTION:
                    widget = self.widgets[event.motion.windowID]
                    widget.payload.mouse_motion(event.motion.x, event.motion.y)
                elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                    widget = self.widgets[event.button.windowID]
                    widget.payload.mouse_button_down(event.button.x, event.button.y, event.button.button)
                elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                    widget = self.widgets[event.button.windowID]
                    widget.payload.mouse_button_up(event.button.x, event.button.y, event.button.button)
                elif event.type == sdl2.SDL_KEYDOWN:
                    widget = self.widgets[event.key.windowID]
                    widget.payload.key_down(event.key.keysym.sym, bool(event.key.repeat))
                elif event.type == sdl2.SDL_KEYUP:
                    widget = self.widgets[event.key.windowID]
                    widget.payload.key_up(event.key.keysym.sym)
                elif event.type == sdl2.SDL_WINDOWEVENT:
                    widget = self.widgets.get(event.window.windowID)
                    if event.window.event == sdl2.video.SDL_WINDOWEVENT_CLOSE:
                        if widget.payload.closing():
                            if widget is root:
                                self.transport.close()
                                for widget in list(self.widgets.values()):
                                    widget.payload.close()
                                    widget.window.close()
                                    self.widgets.pop(widget.uid)
                                self.running = False
                            else:
                                widget.payload.close()
                                widget.window.close()
                                self.widgets.pop(widget.uid)

        #sdl2.SDL_PauseAudio(1)
        for plugin in list(self.plugins.plugins):
            plugin.close()
        sdl2.ext.quit()

class Widget:
    def __init__(self, title, width, height, mk_payload, *payload_args):
        self.width = width
        self.height = height
        self.window = sdl2.ext.Window(title, (width, height))
        self.uid = sdl2.SDL_GetWindowID(self.window.window)
        self.exposed = True
        self.payload = mk_payload(self, *payload_args)
        self.window.show()

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

    def key_down(self, sym, repeat):
        pass

    def key_up(self, sym):
        pass

    def closing(self):
        return True

    def close(self):
        pass

class MainPayload:
    def __init__(self, widget, editor):
        self.editor = editor
        self.renderer = cairo_renderer.Renderer(widget)
        self.ctx = cairo.Context(self.renderer.surface)
        self.hit = gui.Hit()

    def draw(self):
        widget = self.renderer.widget
        hit = self.hit = gui.Hit()
        ctx = self.ctx
        ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        ctx.rectangle(0, 0, widget.width, widget.height)
        ctx.fill()
        self.quickdraw()
        self.renderer.flip()

        vu_meter = gui.Box(10, 10, 20, 10)
        def _click_(x, y, button):
            self.editor.transport.volume_meter.clipping0 = False
            self.editor.transport.volume_meter.clipping1 = False
            return True
        vu_meter.on_button_down = _click_
        hit.append(vu_meter)

        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.rectangle(10, 110, 80, 15)
        ctx.stroke()
        ctx.move_to(20, 122)
        ctx.show_text(self.editor.plugin.name)
        plugin_button = gui.Box(10, 110, 80, 15)
        def _click_(x, y, button):
            plugin = self.editor.plugin
            if plugin.widget is None:
                self.editor.widget(plugin.name, 120,70, lv2.UIPayload, plugin)
            return True
        plugin_button.on_button_down = _click_
        hit.append(plugin_button)

# line = 120
# split_index = 0
# place = 0
# leveys = 80
# 
#     if main_window in active_windows and expose:
#         expose = False
#         hit_root = gui.Hit()
#         c = gui.Circle(20, 20, 10)
#         def clicker(x, y, button):
#             print('clicked on circle')
#             transport.active_voices.update(map(ActiveVoice, document.track.voices))
#         c.on_button_down = clicker
#         hit_root.append(c)
#         c = gui.Box(300, 300, 250, 250)
#         def clicker(x, y, button):
#             print('clicked on box')
#         c.on_button_down = clicker
#         hit_root.append(c)
# 
#         ctx.select_font_face('sans-serif')
# 
#         ctx.set_source_rgba(0, 0, 0, 1.0)
#         ctx.arc(20, 20, 10, 0, 2*math.pi)
#         ctx.stroke()
# 
#         commands.history_toolbar(history, ctx, hit_root)
#         ctx.set_source_rgba(0.75, 0.75, 0.75, 1.0)
#         for y in range(100, 150, 10):
#           ctx.move_to(10, y)
#           ctx.line_to(1190, y)
#         for y in range(160, 210, 10):
#           ctx.move_to(10, y)
#           ctx.line_to(1190, y)
#         ctx.stroke()
#         ctx.set_source_rgba(0.75, 0.75, 0.75, 1.0)
#         ctx.arc(50, 150, 5, 0, 2*math.pi)
#         ctx.fill()
#         ctx.set_font_size(20)
#         text = "C4"
#         ext = ctx.text_extents(text)
#         ctx.move_to(57, 150 - ext.y_bearing/2)
#         ctx.show_text(text)
#         bar = 57 + ext.width + 2
#         ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
#         ctx.set_font_size(12)
#         ctx.move_to(bar, 100-4)
#         ctx.show_text('1')
#         ctx.move_to(bar, 100)
#         ctx.line_to(bar, 200)
#         ctx.stroke()
#         x = bar + 20
#         #bar = x + 40 * 4 - 20
#         #ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
#         #ctx.move_to(bar, 100)
#         #ctx.line_to(bar, 200)
#         #ctx.stroke()
#         #bar = x + 40 * 8 - 20
#         #ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
#         #ctx.move_to(bar, 100)
#         #ctx.line_to(bar, 200)
#         #ctx.stroke()
#         beats_in_measure = 4
#         def plot_vg(notes, duration, p, this_index):
#                 base, dots, triplet = resolution.categorize_note_duration(duration / 4)
#                 spacing = {
#                     Fraction(2,1): 12,
#                     Fraction(1,1): 7,
#                     Fraction(1,2): 5,
#                     Fraction(1,4): 2,
#                     Fraction(1,8): 1,
#                     Fraction(1,16): 1,
#                     Fraction(1,32): 1,
#                     Fraction(1,64): 1,
#                     Fraction(1,128): 1,
#                 }
#                 if len(notes) == 0:
#                     #ctx.set_font_size(9)
#                     #ctx.move_to(x + p, 150)
#                     #ctx.show_text(str(duration / 4))
#                     ctx.select_font_face('FreeSerif')
#                     ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
#                     ctx.set_font_size(50)
#                     ctx.move_to(x + p - 4, 140-2)
#                     c = {
#                         Fraction(2,1): chr(119098),
#                         Fraction(1,1): chr(119099),
#                         Fraction(1,2): chr(119100),
#                         Fraction(1,4): chr(119101),
#                         Fraction(1,8): chr(119102),
#                         Fraction(1,16): chr(119103),
#                         Fraction(1,32): chr(119104),
#                         Fraction(1,64): chr(119105),
#                         Fraction(1,128): chr(119106),
#                     }[base]
#                     ctx.show_text(c)
#                     ctx.select_font_face('sans-serif')
#                     if triplet:
#                         ctx.move_to(x + p, 135)
#                         ctx.line_to(x + p + 5, 135 + 5)
#                         ctx.line_to(x + p + 5, 135 - 5)
#                         ctx.line_to(x + p, 135)
#                         ctx.stroke()
#                     for dot in range(dots):
#                         ctx.arc(x + p + 16 + dot*5, 135 + 3, 2, 0, 2*math.pi)
#                         ctx.fill()
#                 for note in notes:
#                     rel_y = 32 - note.position
#                     rel_x = p
#                     ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
#                     if note.accidental is not None:
#                         char_accidental = {
#                           -2: chr(119083),
#                           -1: chr(0x266d),
#                            0: chr(0x266e),
#                           +1: chr(0x266f),
#                           +2: chr(119082),
#                         }
#                         ctx.select_font_face('FreeSerif')
#                         ctx.set_font_size(25)
#                         xt = ctx.text_extents(char_accidental[note.accidental])
#                         ctx.move_to(x + rel_x - 8 - xt.width, 150 + rel_y*5 + 5)
#                         ctx.show_text(char_accidental[note.accidental])
#                         ctx.select_font_face('sans-serif')
#                     if triplet:
#                         ctx.move_to(x + rel_x-5, 150 + rel_y*5)
#                         ctx.line_to(x + rel_x+5, 150 + rel_y*5 + 5)
#                         ctx.line_to(x + rel_x+5, 150 + rel_y*5 - 5)
#                     else:
#                         ctx.move_to(x + rel_x+5, 150 + rel_y*5)
#                         ctx.arc(x + rel_x, 150 + rel_y*5, 5, 0, 2*math.pi)
#                     if base >= Fraction(1, 2):
#                         ctx.stroke()
#                     else:
#                         ctx.fill()
#                     for dot in range(dots):
#                         ctx.arc(x + rel_x + 8 + dot*5, 150 + rel_y*5 + 3, 2, 0, 2*math.pi)
#                         ctx.fill()
#                 if len(notes) > 0:
#                     high = min(150 + (32 - n.position)*5 for n in notes)
#                     low = max(150 + (32 - n.position)*5 for n in notes)
#                     if high < low:
#                         ctx.move_to(x + rel_x + 5, high)
#                         ctx.line_to(x + rel_x + 5, low)
#                         ctx.stroke()
#                     if base <= Fraction(1, 2):
#                         ctx.move_to(x + rel_x + 5, high)
#                         ctx.line_to(x + rel_x + 5, high - 30)
#                         ctx.stroke()
#                     for k in range(5):
#                         if base <= Fraction(1, 2**(k+3)):
#                             ctx.move_to(x + rel_x + 5, high - 30 + k * 4)
#                             ctx.line_to(x + rel_x + 5 + 5, high - 30 + k * 4 + 8)
#                             ctx.stroke()
#                 #ctx.set_source_rgba(1,0,0,0.2)
#                 #ctx.rectangle(x + p, 85, spacing[base] * 20 + 20, 135)
#                 #ctx.fill()
#                 box = gui.Box(x+p - 20, 85, spacing[base] * 20 + 20, 135)
#                 t = x
#                 def h(_, __):
#                     global split_index, place, leveys
#                     split_index = this_index
#                     place = t + p - 20
#                     leveys = spacing[base] * 20 + 20
#                     return True
#                 box.on_hover = h
#                 hit_root.append(box)
#                 return spacing[base] * 20 + 20
#         for voice in document.track.voices:
#             p = 0
#             beat_phase = 0
#             bar_index = 2
#             for ti, vg in enumerate(voice):
#                 duration = vg.duration
#                 while beat_phase + duration > 4:
#                     t = p
#                     thisd = 4 - beat_phase
#                     duration -= thisd
#                     p += plot_vg(vg.notes, thisd, p, ti)
#                     beat_phase = (beat_phase + thisd) % beats_in_measure
#                     if beat_phase == 0:
#                         bar = x + p - 20
#                         ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
#                         ctx.set_font_size(12)
#                         ctx.move_to(bar, 100-4)
#                         ctx.show_text(str(bar_index))
#                         bar_index += 1
#                         ctx.move_to(bar, 100)
#                         ctx.line_to(bar, 200)
#                         ctx.stroke()
#                     for note in vg.notes:
#                         ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
#                         rel_y = 32 - note.position
#                         ctx.move_to(x+t+8, 150 + rel_y*5 + 3)
#                         ctx.curve_to(x+t+8, 158 + rel_y*5 + 3,
#                                      x+p-8, 158 + rel_y*5 + 3,
#                                      x+p-8, 150 + rel_y*5 + 3)
#                         ctx.stroke()
#                 p += plot_vg(vg.notes, duration, p, ti)
#                 beat_phase = (beat_phase + duration) % beats_in_measure
#                 if beat_phase == 0:
#                     bar = x + p - 20
#                     ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
#                     ctx.set_font_size(12)
#                     ctx.move_to(bar, 100-4)
#                     ctx.show_text(str(bar_index))
#                     bar_index += 1
#                     ctx.move_to(bar, 100)
#                     ctx.line_to(bar, 200)
#                     ctx.stroke()
# 
#         total = document.track.voices[0][split_index].duration / 4
#         ctx.set_source_rgba(1,1,1,1)
#         ctx.rectangle(place, 100, leveys, 100)
#         ctx.fill()
#         ctx.set_source_rgba(0,0,0,1)
#         ctx.rectangle(place, 100, leveys, 100)
#         ctx.stroke()
#         ctx.set_source_rgba(0.7,0.7,0.7,1)
#         ctx.move_to(line, 100)
#         ctx.line_to(line, 100+100)
#         ctx.stroke()
#         ctx.set_source_rgba(0,0,0,1)
#         h = gui.Box(place, 100, leveys, 100)
#         def f(x, y):
#             global line
#             ia = resolution.quantize_fraction((x - place) / leveys * float(total))
#             ib = total - ia
#             if ib in resolution.generate_all_note_durations():
#                 line = x
#                 return True
#         h.on_hover = f
#         def g(x,y,button):
#             ia = resolution.quantize_fraction((line - place) / leveys * float(total))
#             ib = total - ia
#             if ib in resolution.generate_all_note_durations():
#                 print('splitting')
#                 n1 = list(document.track.voices[0][split_index].notes)
#                 n2 = list(document.track.voices[0][split_index].notes)
#                 document.track.voices[0][split_index:split_index+1] = [
#                     VoiceGlyph(n1, ia * 4),
#                     VoiceGlyph(n2, ib * 4),
#                 ]
#                 return True
#         h.on_button_down = g
#         hit_root.append(h)
# 
#         a = resolution.quantize_fraction((line - place) / leveys * float(total))
#         b = total - a
#         tab = {
#             Fraction(2,1): chr(119132),
#             Fraction(1,1): chr(119133),
#             Fraction(1,2): chr(119134),
#             Fraction(1,4): chr(119135),
#             Fraction(1,8): chr(119136),
#             Fraction(1,16): chr(119137),
#             Fraction(1,32): chr(119138),
#             Fraction(1,64): chr(119139),
#             Fraction(1,128): chr(119140),
#         }
#         if b in resolution.generate_all_note_durations():
#             ctx.select_font_face('FreeSerif')
#             ctx.set_font_size(25)
#             base, dots, triplet = resolution.categorize_note_duration(a)
#             ctx.move_to(place + 5, 100 + 30)
#             ctx.show_text(tab[base] + '.'*dots)
#             ctx.set_font_size(12)
#             ctx.move_to(place + 5, 100 + 42)
#             ctx.show_text('3'*int(triplet))
#             ctx.set_font_size(25)
#             base, dots, triplet = resolution.categorize_note_duration(b)
#             text = tab[base] + '.'*dots
#             ex = ctx.text_extents(text)
#             ctx.move_to(place + leveys - 5 - ex.width, 100 + 30)
#             ctx.show_text(text)
#             ctx.set_font_size(12)
#             ctx.move_to(place + leveys - 5 - ex.width, 100 + 42)
#             ctx.show_text('3'*int(triplet))
# 
#                 if i == parent_window_id:
#                     entities.save_document('document.mide.zip', document)

    def update(self):
        if not self.renderer.widget.exposed:
            self.quickdraw()
            self.renderer.flip()

    def quickdraw(self):
        meter = self.editor.transport.volume_meter
        ctx = self.ctx
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.rectangle(10, 10, 20, 90)
        ctx.fill()
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        if meter.volume0 > 0:
            dbfs = 20 * math.log10(meter.volume0)
            v0 = min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            v0 = 0.0
        ctx.rectangle(11, 20+80 - 80*v0, 8, 80*v0)
        ctx.fill()
        if meter.volume1 > 0:
            dbfs = 20 * math.log10(meter.volume1)
            v1 = min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            v1 = 0.0
        ctx.rectangle(21, 20+80 - 80*v1, 8, 80*v1)
        ctx.fill()
        ctx.set_source_rgba(1.0, 0.0, 0.0, 1.0)
        if meter.clipping0:
            ctx.rectangle(10, 10, 10, 10)
        if meter.clipping1:
            ctx.rectangle(20, 10, 10, 10)
        ctx.fill()
        

                    #expose = expose or hit_root.hit(x, y).on_button_up(x,y,event.button.button)
    def mouse_motion(self, x, y):
        exposed = self.hit.hit(x, y).on_hover(x, y)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def mouse_button_down(self, x, y, button):
        exposed = self.hit.hit(x, y).on_button_down(x, y, button)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def mouse_button_up(self, x, y, button):
        exposed = self.hit.hit(x, y).on_button_up(x, y, button)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def key_down(self, sym, repeat):
        if not repeat:
            @self.editor.plugin.event
            def _event_():
                buf = self.editor.plugin.inputs['In']
                self.editor.plugin.push_midi_event(buf, [0x91, sym % 128, 0xFF])

    def key_up(self, sym):
        @self.editor.plugin.event
        def _event_():
            buf = self.editor.plugin.inputs['In']
            self.editor.plugin.push_midi_event(buf, [0x81, sym % 128, 0xFF])

    def closing(self):
        return True

    def close(self):
        self.renderer.close()

if __name__=='__main__':
    Editor().ui()
