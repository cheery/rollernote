import sdl2.ext
import entities
import cairo_renderer
import cairo
import lv2
import audio
import commands
import gui
import math
import resolution
import bisect
import dialogs
import random
import components
from fractions import Fraction

@gui.composable
def label(text, x, y, font_size=20):
    @gui.drawing
    def _draw_(ui, comp):
        ui.ctx.set_font_size(font_size)
        ui.ctx.move_to(x, y)
        ui.ctx.show_text(text)

@gui.composable
def app(editor): 
    gui.workspace(color=(1,1,1,1), font_family='FreeSerif')
    status = gui.state("program started")

    # Editor history
    history = editor.history

    undo = components.button(chr(0x21B6), font_size=24, disabled=len(history.undo_stack) == 0)
    undo.shape = gui.Box(100, 10, 32, 32)
    @undo.listen(gui.e_motion)
    def _undo_status_(x, y):
        if len(history.undo_stack) > 0:
            status.value = f"undo: {history.undo_stack[-1].name}"
    @undo.listen(gui.e_button_down)
    def _undo_down_(x, y, button):
        if len(history.undo_stack) > 0:
             status.value = f"undone: {history.undo_stack[-1].name}"
             history.undo()
             undo.set_dirty()
             redo.set_dirty()

    redo = components.button(chr(0x21B7), font_size=24, disabled=len(history.redo_stack) == 0)
    redo.shape = gui.Box(133, 10, 32, 32)
    @redo.listen(gui.e_motion)
    def _redo_status_(x, y):
        if len(history.redo_stack) > 0:
            status.value = f"redo: {history.redo_stack[-1].name}"
    @redo.listen(gui.e_button_down)
    def _redo_down_(x, y, button):
        if len(history.redo_stack) > 0:
             status.value = f"redone: {history.redo_stack[-1].name}"
             history.redo()
             undo.set_dirty()
             redo.set_dirty()

    play = components.button(chr(0x25B6), font_size=32)
    play.shape = gui.Box(100, 52, 32, 32)
    @play.listen(gui.e_button_down)
    def _play_down_(x, y, button):
        bpm = audio.LinearEnvelope([ (0, 80, 0) ])
        assert bpm.check_positiveness()
        editor.transport.live_voices.update([
            audio.LiveVoice(editor.plugin, voice.segments, bpm)
            for voice in editor.document.track.voices
        ])

    save = components.button("save", font_size=32)
    save.shape = gui.Box(142, 52, 32*3, 32)
    @save.listen(gui.e_button_down)
    def _save_down_(x, y, button):
        instrument = editor.document.instrument
        instrument.patch, instrument.data = editor.plugin.save()
        entities.save_document('document.mide.zip', editor.document)
 
    new = components.button("new", font_size=32)
    new.shape = gui.Box(142, 20+32*2, 32*3, 32)
    @new.listen(gui.e_button_down)
    def _new_down_(x, y, button):
        # TODO: Also clean up audio params!
        sdl2.SDL_PauseAudio(1)
        for plugin in list(editor.plugins.plugins):
            plugin.close()
        sdl2.SDL_PauseAudio(0)
        editor.document = entities.Document(
            track = entities.Track(
                graphs = [
                    entities.Staff(100, 3, 2, [
                        entities.StaffBlock(
                            beat = 0,
                            beats_in_measure = random.choice([3,4]),
                            beat_unit = 4,
                            canonical_key = random.randrange(-7, 8),
                            clef = 3,
                            mode = None
                        )
                    ])
                ],
                voices = [
                    entities.Voice(200, 100, [])
                ]
            ),
            instrument = entities.Instrument(
                plugin = "https://surge-synthesizer.github.io/lv2/surge-xt",
                patch = {},
                data = {}
            )
        )
        editor.plugin = editor.plugins.plugin(editor.document.instrument.plugin)

    splitbutton = components.button("split", font_size=32)
    splitbutton.shape = gui.Box(152+32*3, 52, 32*2, 32)
#        def _click_(x, y, button):
#            self.tool = SplittingTool(self.editor.document)

    plotbutton = components.button("plot", font_size=32)
    plotbutton.shape = gui.Box(172+32*6, 52, 32*2, 32)
#        def _click_(x, y, button):
#            self.tool = NoteTool(self, self.editor.document)

#        vu_meter = gui.Box(10, 10, 20, 10)
#        def _click_(x, y, button):
#            self.editor.transport.volume_meter.clipping0 = False
#            self.editor.transport.volume_meter.clipping1 = False
#            return True
#        vu_meter.on_button_down = _click_
#        hit.append(vu_meter)
#
#        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
#        ctx.set_font_size(10)
#        ctx.rectangle(10, 110, 80, 15)
#        ctx.stroke()
#        ctx.move_to(20, 122)
#        ctx.show_text(self.editor.plugin.name)
#        plugin_button = gui.Box(10, 110, 80, 15)
#        def _click_(x, y, button):
#            plugin = self.editor.plugin
#            if plugin.widget is None:
#                self.editor.widget(plugin.name, 120,70, lv2.UIPayload, plugin)
#            return True
#        plugin_button.on_button_down = _click_
#        hit.append(plugin_button)


    counter = gui.state(0)
    hmm = components.button(f"hello {counter.value}")
    hmm.shape = gui.Box(10, 52, 100, 20)
    @hmm.listen(gui.e_button_down)
    def _click_(x, y, button):
        counter.value += 1
    src = gui.state('foobar')
    haa = components.textbox(src.value, src.set_state)
    haa.shape = gui.Box(10+110, 52, 100, 20)


    widget = gui.ui.get().widget
    label(status.value, 0, widget.height - 3)

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

    def widget(self, *args):
        widget = Widget(*args)
        self.widgets[widget.uid] = widget
        return widget

    def ui(self):
        self.running = True
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_AUDIO)

        root = self.widget("rollernote", 1200, 700, gui.GUI, app, self)
        #root = self.widget("rollernote", 1200, 700, MainPayload, self)
        sdl2.SDL_StartTextInput()

        while self.running:
            self.time = sdl2.SDL_GetTicks64() / 1000.0

            for widget in self.widgets.values():
                widget.payload.update()
                if widget.exposed:
                    widget.exposed = False
                    widget.payload.draw()
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
                elif event.type == sdl2.SDL_TEXTINPUT:
                    widget = self.widgets[event.text.windowID]
                    text = event.text.text.decode('utf-8')
                    widget.payload.text_input(text)
                elif event.type == sdl2.SDL_KEYDOWN:
                    widget = self.widgets[event.key.windowID]
                    widget.payload.key_down(event.key.keysym.sym, bool(event.key.repeat), event.key.keysym.mod)
                elif event.type == sdl2.SDL_KEYUP:
                    widget = self.widgets[event.key.windowID]
                    widget.payload.key_up(event.key.keysym.sym, event.key.keysym.mod)
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

        sdl2.SDL_StopTextInput()
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

class MainPayload:
    def __init__(self, widget, editor):
        self.editor = editor
        self.renderer = cairo_renderer.Renderer(widget)
        self.ctx = cairo.Context(self.renderer.surface)
        self.hit = gui.Hit()

        self.tool = NoteTool(self, editor.document)
        self.dialog = dialogs.TextDialog(self.ctx, "HELLO", 20, 50, 50, 300, 50)

    def draw(self):
        widget = self.renderer.widget
        hit = self.hit = gui.Hit()
        ctx = self.ctx
        ctx.select_font_face('FreeSerif')
        ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        ctx.rectangle(0, 0, widget.width, widget.height)
        ctx.fill()

        commands.history_toolbar(self.editor.history, ctx, hit)

        bb = gui.Box(100, 20+32, 32, 32)
        def _button_down_(x, y, button):
            bpm = audio.LinearEnvelope([ (0, 80, 0) ])
            assert bpm.check_positiveness()
            self.editor.transport.live_voices.update([
                audio.LiveVoice(self.editor.plugin, voice.segments, bpm)
                for voice in self.editor.document.track.voices
            ])
            return False
        bb.on_button_down = _button_down_
        hit.append(bb)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(32)
        bb.trace(ctx)
        ctx.stroke()
        ctx.move_to(103, 20+32+28)
        ctx.show_text(chr(0x25B6))

        bb = gui.Box(132+10, 20+32, 32*3, 32)
        def _click_(x, y, button):
            instrument = self.editor.document.instrument
            instrument.patch, instrument.data = self.editor.plugin.save()
            entities.save_document('document.mide.zip', self.editor.document)
            return False
        bb.on_button_down = _click_
        hit.append(bb)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(32)
        bb.trace(ctx)
        ctx.stroke()
        ctx.move_to(132+10, 20+32+28)
        ctx.show_text("save")

        bb = gui.Box(132+10, 20+32*2, 32*3, 32)
        def _click_(x, y, button):
            # TODO: Also stop playback!!
            for plugin in list(self.editor.plugins.plugins):
                plugin.close()
            self.editor.document = entities.Document(
                track = entities.Track(
                    graphs = [
                        entities.Staff(100, 3, 2, [
                            entities.StaffBlock(
                                beat = 0,
                                beats_in_measure = random.choice([3,4]),
                                beat_unit = 4,
                                canonical_key = random.randrange(-7, 8),
                                clef = 3,
                                mode = None
                            )
                        ])
                    ],
                    voices = [
                        entities.Voice(200, 100, [])
                    ]
                ),
                instrument = entities.Instrument(
                    plugin = "https://surge-synthesizer.github.io/lv2/surge-xt",
                    patch = {},
                    data = {}
                )
            )
            self.editor.plugin = self.editor.plugins.plugin(self.editor.document.instrument.plugin)
            return True
        bb.on_button_down = _click_
        hit.append(bb)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(32)
        ctx.rectangle(132+10, 20+32*2, 32*3, 32)
        ctx.stroke()
        ctx.move_to(132+10, 20+32*2+28)
        ctx.show_text("new")

        bb = gui.Box(132+20+32*3, 20+32, 32*2, 32)
        def _click_(x, y, button):
            self.tool = SplittingTool(self.editor.document)
            return False
        bb.on_button_down = _click_
        hit.append(bb)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(32)
        ctx.rectangle(132+20+32*3, 20+32, 32*2, 32)
        ctx.stroke()
        ctx.move_to(132+20+32*3, 20+32+28)
        ctx.show_text("split")

        bb = gui.Box(132+40+32*6, 20+32, 32*2, 32)
        def _click_(x, y, button):
            self.tool = NoteTool(self, self.editor.document)
            return False
        bb.on_button_down = _click_
        hit.append(bb)
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(32)
        ctx.rectangle(132+40+32*6, 20+32, 32*2, 32)
        ctx.stroke()
        ctx.move_to(132+40+32*6, 20+32+28)
        ctx.show_text("plot")

        vu_meter = gui.Box(10, 10, 20, 10)
        def _click_(x, y, button):
            self.editor.transport.volume_meter.clipping0 = False
            self.editor.transport.volume_meter.clipping1 = False
            return True
        vu_meter.on_button_down = _click_
        hit.append(vu_meter)

        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(10)
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

        document = self.editor.document
        views = {}
        y_base = 150
        for staff in document.track.graphs:
            view = StaffView(staff, y_base)

            initial = view.by_beat(0.0)
            canon_key = initial.canonical_key
            clef = initial.clef
            key = resolution.canon_key(canon_key)

            ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)

            # Margins to fit everything in
            def shifted_positions():
                for voice in document.track.voices:
                    beat = 0.0
                    for seg in voice.segments:
                        block = view.by_beat(beat)
                        for pitch in seg.notes:
                            yield pitch.position - staff.bot*12 - block.clef
                        beat += float(seg.duration)
            positions = list(shifted_positions())
            margin_bot = staff.bot + min(min(positions, default=0) // 12, 0)
            margin_top = max(staff.top, staff.bot + (max(positions, default=0) // 12))

            # Staff lines
            # These are rendered without refering
            # to anything else but staff.top and staff.bot and margins
            start = (margin_top - staff.top)*12+2
            stop = (margin_top - staff.bot)*12+2
            for i in range(start, stop, 2):
                if i % 12 != 2:
                    k = i * 5
                    ctx.move_to(0, y_base+k)
                    ctx.line_to(self.renderer.widget.width, y_base+k)
                    ctx.stroke()
            span = (margin_top - margin_bot)*12+4
            view.height = span * 5
            #ctx.set_source_rgba(0.5, 0.5, 1.0, 1.0)
            #ctx.move_to(0, y_base)
            #ctx.line_to(self.renderer.widget.width, y_base)
            #ctx.move_to(0, y_base+height)
            #ctx.line_to(self.renderer.widget.width, y_base+height)
            #ctx.stroke()

            # The reference note is staff.bot*12-clef
            view.reference = (stop+1) * 5 + y_base
            #ctx.move_to(0, view.reference)
            #ctx.line_to(self.renderer.widget.width, view.reference)
            #ctx.stroke()

            # Major/Minor letters above the 'clef'
            major = resolution.tonic(canon_key)
            minor = resolution.tonic(canon_key, 5)
            major_text = resolution.pitch_name(major, key, show_octave=False)
            minor_text = resolution.pitch_name(minor, key, show_octave=False)
            ctx.set_font_size(10)
            ctx.move_to(35, y_base + 9)
            ctx.show_text(f"{major_text} {minor_text}m")

            # Initial pitch markings
            ctx.set_font_size(10)
            for i in range(0, span, 2):
                position = i + margin_bot*12 + clef
                t = resolution.pitch_name(entities.Pitch(position), key)
                ctx.move_to(10, view.note_position(0.0, position)+4)
                ctx.show_text(t)

            y_base += view.height + 10

            views[staff.uid] = view

        # Layout calculation begins
        for view in views.values():
            margin = 35
            block = view.by_beat(0.0)
            if block.clef is not None:
                margin += 50
            if block.canonical_key is not None:
                canon_key = block.canonical_key
                margin += abs(canon_key) * 7
            #if block.beats_in_measure is not None or block.beat_unit is not None:
            #    pass
            margin += 30
            view.left_margin = margin

        def staff_block(view, x, block, full_block):
            if block.clef is not None:
                # Our version of a clef
                # Select most centered C, F, G in the staff
                ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
                ctx.set_font_size(20)
                i = (staff.top*6 + staff.bot*6) + block.clef + 1
                j = i - i % 7
                p = min((j + x for x in [-7, -4, -3, 0, 3, 4] if (j + x - block.clef) % 2 == 1),
                        key = lambda p: abs(p - i))
                y = view.note_position(block.beat, p)
                t = resolution.pitch_name(entities.Pitch(p))
                ctx.move_to(x + 5 + 7, y+7)
                ctx.show_text(t)
                ctx.arc(x + 5, y, 5, 0, 2*math.pi)
                ctx.fill()

                #ctx.arc(x + 15, note_position(block.beat, i), 5, 0, 2*math.pi)
                #ctx.fill()
                x += 40

            if block.canonical_key is not None:
                canon_key = block.canonical_key
                # Key signature
                ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
                ctx.set_font_size(25)
                # The vertical positioning of accidentals is awful at the moment,
                # but blame people who call you stupid when you ask
                # what is behind vertical positioning of accidentals.
                if canon_key >= 0:
                    for sharp in resolution.sharps[:canon_key]:
                        for i in range(staff.bot, staff.top):
                            position = i*12 + full_block.clef + 11
                            c_pos = position - position % 7
                            if c_pos + 4 >= position + 2:
                                j = c_pos + sharp - 7
                            else:
                                j = c_pos + sharp - 7 * (sharp > 4)
                            ctx.move_to(x, view.note_position(block.beat, j)+4)
                            ctx.show_text(resolution.char_accidental[1])
                        x += 7
                else:
                    for flat in reversed(resolution.sharps[canon_key:]):
                        for i in range(staff.bot, staff.top):
                            position = i*12 + full_block.clef + 11
                            j = (position - position % 7) + flat - 7 * (flat > 2)
                            # It is questionable to move them around like this,
                            # It seems that more likely there are several fixed patterns
                            # and one is used when it fits the best.
                            if j > position:
                                 j -= 7
                            if j <= position - 10:
                                 j += 7
                            ctx.move_to(x, view.note_position(block.beat, j)+4)
                            ctx.show_text(resolution.char_accidental[-1])
                        x += 7

            if block.beats_in_measure is not None or block.beat_unit is not None:
                ctx.set_source_rgba(0, 0, 0, 1)
                ctx.set_font_size(25)
                for i in range(staff.bot, staff.top):
                    position = i*12 + 7
                    ctx.set_font_size(25)
                    ctx.move_to(x + 10, view.graph_point(position)-2)
                    ctx.show_text(str(full_block.beats_in_measure))
                    ctx.move_to(x + 10, view.graph_point(position)+18)
                    ctx.show_text(str(full_block.beat_unit))
            x += 30
            return x

        x = max(view.left_margin for view in views.values())

        for view in views.values():
            block = view.by_beat(0.0)
            staff_block(view, x - view.left_margin + 35, block, block)

            # bar
            ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
            ctx.move_to(x, view.graph_point(staff.top*12 - 1))
            ctx.line_to(x, view.graph_point(staff.bot*12 + 3))
            ctx.stroke()

        x += 20

        # Spacing configuration for note heads
        p = 20 # width of 1/128th note
        q = 50 # width of 1/1 note
        a = math.log(p / q) / math.log(1 / 128)

        # Computing positioning data for empty segments
        # from their empty neighbours
        def mean(xs):
            xs = list(xs)
            return sum(xs) // len(xs)
        empty_segment_position = {}
        for voice in document.track.voices:
            view = views[voice.staff_uid]
#        last_note_position = None
#        rest_positions = []
#
#        # Forward pass
#        for seg in voice:
#            if len(seg.notes) == 0:
#                # Store empty segment for later processing
#                rest_positions.append(seg)
#            else:
#                # Calculate mean position for current notes
#                note_position = mean(pitch.position for pitch in seg.notes)
#                
#                # Assign this position to previous empty segments
#                for rest_seg in rest_positions:
#                    if rest_seg not in empty_segment_position:
#                        empty_segment_position[rest_seg] = []
#                    if last_note_position is not None:
#                        empty_segment_position[rest_seg].append(last_note_position)
#                    empty_segment_position[rest_seg].append(note_position)
#                
#                # Clear list of rest positions
#                rest_positions = []
#                last_note_position = note_position
            position = None
            for seg in voice.segments:
                if len(seg.notes) == 0:
                    if position is None:
                        empty_segment_position[seg] = []
                    else:
                        empty_segment_position[seg] = [position]
                else:
                    position = mean(pitch.position for pitch in seg.notes)
            position = None
            beat = 0
            for seg in reversed(voice.segments):
                if len(seg.notes) == 0:
                    if position is None:
                        positions = empty_segment_position[seg]
                        if len(positions) == 0:
                            block = view.by_beat(beat)
                            i = (staff.top*6 + staff.bot*6) + block.clef + 1
                            positions.append(i)
                    else:
                        empty_segment_position[seg].append(position)
                else:
                    position = mean(pitch.position for pitch in seg.notes)
                beat += float(seg.duration)
#        # If rest positions are left over, fill them using the last known note position
#        for rest_seg in rest_positions:
#            if rest_seg not in empty_segment_position:
#                empty_segment_position[rest_seg] = []
#            if last_note_position is not None:
#                empty_segment_position[rest_seg].append(last_note_position)
#            else:
#                # Default to center if no notes were found
#                empty_segment_position[rest_seg].append((low_staff + high_staff) // 2)
        for seg, positions in empty_segment_position.items():
            empty_segment_position[seg] = mean(positions)

        # Events on the line
        events = []
        E_SEGMENT = 2
        E_BLOCK = 1
        E_BARLINE = 0
        def insert_event(beat, kind, value):
            bisect.insort_left(events, (beat, kind, value), key=lambda k: (k[0], k[1]))
        # Breaking segments into measures
        def beats_in_this_measure(view, beat):
            this, future = entities.at_beat(view.blocks, beat)
            if future is None:
                return this.beats_in_measure, False
            else:
                distance = future.beat - beat
                if distance < this.beats_in_measure:
                    return distance, True
                else:
                    return this.beats_in_measure, False
        measured_voices = []
        for voice in document.track.voices:
            view = views[voice.staff_uid]
            measures = []
            measure = []
            beat = 0.0
            remain, _ = beats_in_this_measure(view, beat)
            for seg in voice.segments:
                duration = seg.duration
                while remain < duration:
                    if remain > 0:
                        insert_event(beat, E_SEGMENT, (remain, seg, view))
                        duration -= remain
                        beat += float(remain)
                        measure.append((remain, seg))
                    measures.append(measure)
                    remain, _ = beats_in_this_measure(view, beat)
                    measure = []
                if duration != 0: # seg.duration <= remain
                    insert_event(beat, E_SEGMENT, (duration, seg, view))
                    remain -= duration
                    beat += float(duration)
                    measure.append((duration, seg))
            view.highest_beat = max(view.highest_beat, beat)
            measures.append(measure)
            measured_voices.append(measures)
        def frange(start, stop, step):
            current = start
            while current < stop:
                yield current
                current += step
        # Inserting blocks into event stream
        for view in views.values():
            previous = view.blocks[0]
            for i, block in enumerate(view.blocks[1:], 1):
                for stop in frange(previous.beat + previous.beats_in_measure, block.beat, previous.beats_in_measure):
                    insert_event(stop, E_BARLINE, view)
                rawblock = view.staff.blocks[i]
                unusual = (block.beat - previous.beat) % previous.beats_in_measure != 0
                insert_event(block.beat, E_BLOCK, (view, rawblock, block, unusual))
                previous = block
            for stop in frange(previous.beat + previous.beats_in_measure, view.highest_beat, previous.beats_in_measure):
                insert_event(stop, E_BARLINE, view)

        # Layout data to draw ties
        layout = {}
        # Offsets and corresponding beat for drawing segment boxes
        offsets = [x]
        beats = [0.0]
        beat = 0.0
        push0 = 0 # Additional pushes from other items.
        push1 = 0
        # "Efficient algorithms for music engraving,
        #  focusing on correctness"
        for time, which, value in events:
            if which == E_BLOCK and push0 > 0:
                x += push0
                push0 = 0
            if which == E_SEGMENT and push0 + push1 > 0:
                x += push0 + push1
                push0 = push1 = 0
                offsets.append(x)
                beats.append(beat)
            if beat < time:
                x += q * ((time - beat) / beat_unit) ** a
                beat = time
                offsets.append(x)
                beats.append(beat)
            if which == E_BLOCK:
                view, rawblock, block, unusual = value
                if unusual:
                    ctx.set_dash([1, 1])
                    ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                    ctx.move_to(x, view.graph_point(staff.top*12 - 1))
                    ctx.line_to(x, view.graph_point(staff.bot*12 + 3))
                    ctx.stroke()
                    ctx.set_dash([])
                    pushk = staff_block(view, x + 10, rawblock, block) - x
                else:
                    pushk = 10 + staff_block(view, x, rawblock, block) - x
                push1 = max(push1, pushk)
            if which == E_BARLINE:
                view = value
                ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                ctx.move_to(x, view.graph_point(staff.top*12 - 1))
                ctx.line_to(x, view.graph_point(staff.bot*12 + 3))
                ctx.stroke()
                push0 = 10
            if which == E_SEGMENT:
                ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
                duration, seg, view = value
                beat_unit = view.by_beat(beat).beat_unit
                cat = resolution.categorize_note_duration(duration / beat_unit)
                if cat is None:
                    if len(seg.notes) == 0:
                        t = empty_segment_position[seg]
                    else:
                        t = mean(pitch.position for pitch in seg.notes)
                    t = (t - t % 12) - 6
                    y = view.note_position(beat, t)
                    ctx.set_font_size(10)
                    ctx.move_to(x - 4, y -2)
                    ctx.show_text(f'|{duration / beat_unit}|')
                    d = resolution.quantize_fraction(duration / beat_unit)
                    cat = resolution.categorize_note_duration(d)

                if True:
                    base, dots, triplet = cat
                    if len(seg.notes) == 0:
                        t = empty_segment_position[seg]
                        t = (t - t % 12) - 6
                        y = view.note_position(beat, t)
                        ctx.set_font_size(50)
                        ctx.move_to(x - 4, y -2)
                        c = {
                            Fraction(2,1): chr(119098),
                            Fraction(1,1): chr(119099),
                            Fraction(1,2): chr(119100),
                            Fraction(1,4): chr(119101),
                            Fraction(1,8): chr(119102),
                            Fraction(1,16): chr(119103),
                            Fraction(1,32): chr(119104),
                            Fraction(1,64): chr(119105),
                            Fraction(1,128): chr(119106),
                        }[base]
                        ctx.show_text(c)
                        if triplet:
                            ctx.move_to(x, 135)
                            ctx.line_to(x + 5, 150 + k + 5)
                            ctx.line_to(x + 5, 150 + k - 5)
                            ctx.line_to(x, 150 + k)
                            ctx.stroke()
                        for dot in range(dots):
                            ctx.arc(x + 16 + dot*5, 150 + k + 3, 2, 0, 2*math.pi)
                            ctx.fill()
                    for pitch in seg.notes:
                        y = view.note_position(beat, pitch.position)
                        # TODO: render accidental only when it changes in measure.
                        if pitch.accidental is not None:
                            ctx.set_font_size(25)
                            xt = ctx.text_extents(resolution.char_accidental[pitch.accidental])
                            ctx.move_to(x - 8 - xt.width, y + 5)
                            ctx.show_text(resolution.char_accidental[pitch.accidental])
                        # TODO: represent triplet with some smarter way
                        if triplet:
                            ctx.move_to(x -5, y)
                            ctx.line_to(x +5, y + 5)
                            ctx.line_to(x +5, y - 5)
                            ctx.line_to(x -5, y - 5)
                        else:
                            ctx.move_to(x +5, y)
                            ctx.arc(x, y, 5, 0, 2*math.pi)
                        if base >= Fraction(1, 2):
                            ctx.stroke()
                        else:
                            ctx.fill()
                        for dot in range(dots):
                            ctx.arc(x + 8 + dot*5, y + 3, 2, 0, 2*math.pi)
                            ctx.fill()
                        if seg in layout:
                            past, px = layout[seg][-1]
                            y0 = view.note_position(past, pitch.position)
                            ctx.move_to(px+8, y0 + 3)
                            ctx.curve_to(px+8, 8 + y0 + 3,
                                         x-8, 8 + y + 3,
                                         x-8, 0 + y + 3)
                            ctx.stroke()
                    if len(seg.notes) > 0:
                        high = min(view.note_position(beat, p.position) for p in seg.notes)
                        low = max(view.note_position(beat, p.position) for p in seg.notes)
                        if high < low:
                            ctx.move_to(x + 5, high)
                            ctx.line_to(x + 5, low)
                            ctx.stroke()
                        if base <= Fraction(1, 2):
                            ctx.move_to(x + 5, high)
                            ctx.line_to(x + 5, high - 30)
                            ctx.stroke()
                        for d in range(5):
                            if base <= Fraction(1, 2**(d+3)):
                                ctx.move_to(x + 5, high - 30 + d * 4)
                                ctx.line_to(x + 5 + 5, high - 30 + d * 4 + 8)
                                ctx.stroke()

                resolution.insert_in_list(layout, seg, (beat, x))

        x += 20
        # bar line
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        ctx.move_to(x, view.graph_point(staff.top*12 - 1))
        ctx.line_to(x, view.graph_point(staff.bot*12 + 3))
        ctx.stroke()

        def monotonic_interpolation(value, sequence, interpolant, use_highest=False):
            li = bisect.bisect_left(sequence, value)
            ri = bisect.bisect_right(sequence, value)
            if li < len(sequence) and sequence[li] == value:
                if use_highest:
                    return interpolant[ri-1]
                else:
                    return interpolant[li]
            lowi = max(0, li - 1)
            uppi = min(len(sequence) - 1, ri)
            if sequence[uppi] != sequence[lowi]:
                t = (value - sequence[lowi]) / (sequence[uppi] - sequence[lowi])
            else:
                t = 0
            return interpolant[lowi]*(1-t) + interpolant[uppi]*t

        # TODO: Come up with better way to broadcast layout details.
        def location_as_position(x, y):
            beat = monotonic_interpolation(x, offsets, beats)
            for view in views.values():
                clef = entities.by_beat(view.blocks, beat).clef
                if view.y <= y < view.y + view.height:
                    return round((view.reference - y) / 5) + staff.bot*12 + clef
        self.location_as_position = location_as_position

        def mk_cb(bb, beat, voice, seg_index, spacing):
            def _hover_(x,y):
                return self.tool.hover_segment(bb, beat, voice, seg_index, spacing, x, y)
            bb.on_hover = _hover_
            def _button_down_(x,y,button):
                return self.tool.button_down_segment(bb, beat, voice, seg_index, spacing, x, y, button)
            bb.on_button_down = _button_down_

        for voice in document.track.voices:
            view = views[voice.staff_uid]
            beat = 0.0
            right = monotonic_interpolation(0.0, beats, offsets)
            for index, seg in enumerate(voice.segments):
                duration = float(seg.duration)
                beat_unit = view.by_beat(beat).beat_unit
                spacing = q * (duration / beat_unit) ** a
                left = monotonic_interpolation(beat, beats, offsets, use_highest=True)
                right = monotonic_interpolation(beat+duration, beats, offsets)
                right = max(right, left + spacing)
                #if beat <= self.loco < beat + duration:
                #    ctx.rectangle(left, 150, zzz-left, (high_bound - low_bound)*5 )
                #    ctx.stroke()
                #low = view.graph_point(staff.top*12 - 1)
                #high = view.graph_point(staff.bot*12 + 3)
                low = view.y
                high = view.y + view.height
                bb = gui.Box(left, low, right-left, high - low )
                mk_cb(bb, beat, voice, index, spacing)
                hit.append(bb)
                beat += duration
            if right < self.renderer.widget.width:
                beat_unit = view.by_beat(beat).beat_unit
                #if beat <= self.loco:
                #    ctx.rectangle(right, 150, self.renderer.widget.width - right, (high_bound - low_bound)*5)
                #    ctx.stroke()
                # On terminal segment, we give a spacing for a single beat and use it for letting user
                # subdivide the terminal segment and create new segments that way.
                spacing = q * (1.0 / beat_unit) ** a
                #low = view.graph_point(staff.top*12 - 1)
                #high = view.graph_point(staff.bot*12 + 3)
                low = view.y
                high = view.y + view.height
                bb = gui.Box(right, low, self.renderer.widget.width - right, high - low)
                mk_cb(bb, beat, voice, -1, spacing)
                hit.append(bb)

        self.tool.draw(ctx, hit)
        if self.dialog is not None:
            self.dialog.draw()

        self.quickdraw()
        self.renderer.flip()

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
        
    def mouse_motion(self, x, y):
        if self.dialog is not None:
            exposed = self.dialog.mouse_motion(x, y)
        else:
            exposed = self.hit.hit(x, y).on_hover(x, y)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def mouse_button_down(self, x, y, button):
        if self.dialog is not None:
            if self.dialog.hit(x, y):
                exposed = self.dialog.mouse_button_down(x, y, button)
            else:
                exposed = True
                self.dialog = None
        else:
            exposed = self.hit.hit(x, y).on_button_down(x, y, button)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def mouse_button_up(self, x, y, button):
        if self.dialog is not None:
            exposed = self.dialog.mouse_button_up(x, y, button)
        else:
            exposed = self.hit.hit(x, y).on_button_up(x, y, button)
        self.renderer.widget.exposed = self.renderer.widget.exposed or exposed

    def text_input(self, text):
        if self.dialog is not None:
            self.dialog.text_input(text)

    def key_down(self, sym, repeat, modifiers):
        if self.dialog is not None:
            exposed = self.dialog.key_down(sym, modifiers)
            self.renderer.widget.exposed = self.renderer.widget.exposed or exposed
        elif not repeat:
            @self.editor.plugin.event
            def _event_():
                buf = self.editor.plugin.inputs['In']
                self.editor.plugin.push_midi_event(buf, [0x91, sym % 128, 0xFF])

    def key_up(self, sym, modifiers):
        if self.dialog is not None:
            exposed = self.dialog.key_up(sym, modifiers)
            self.renderer.widget.exposed = self.renderer.widget.exposed or exposed
        else:
            @self.editor.plugin.event
            def _event_():
                buf = self.editor.plugin.inputs['In']
                self.editor.plugin.push_midi_event(buf, [0x81, sym % 128, 0xFF])

    def closing(self):
        return True

    def close(self):
        self.renderer.close()

class NoteTool:
    def __init__(self, payload, document):
        self.payload = payload
        self.document = document

    def hover_segment(self, bb, beat, voice, seg_index, spacing, x, y):
        pass

    def button_down_segment(self, bb, beat, voice, seg_index, spacing, x, y, button):
        position = self.payload.location_as_position(x, y)
        seg = voice.segments[seg_index]
        if button == 1:
            if not any(pitch.position == position for pitch in seg.notes):
                seg.notes.append(entities.Pitch(position))
                return True
        if button == 3:
            for pitch in seg.notes:
                if pitch.position == position:
                    seg.notes.remove(pitch)
                    return True

    def draw(self, ctx, hit):
        pass

# TODO: Figure out where beat unit can be received from.
class SplittingTool:
    def __init__(self, document):
        self.document = document
        self.primed = False
        self.split_index = 0
        self.split_point = 0.0
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.level = 0
        self.split = None

    def hover_segment(self, bb, beat, voice, seg_index, spacing, x, y):
        if seg_index != self.split_index:
            self.split = None
        self.primed = True
        self.split_index = seg_index
        self.split_point = (x - bb.x) / bb.width
        self.x = bb.x
        self.y = bb.y
        self.width = bb.width
        self.height = bb.height
        self.level = y
        if seg_index != -1:
            total = voice.segments[self.split_index].duration / 4
            a = resolution.quantize_fraction(self.split_point * float(total))
            b = total - a
            if b in resolution.generate_all_note_durations():
                self.split = (a, b)
        else:
            a = resolution.quantize_fraction((x - bb.x) / spacing / 4)
            self.split = (a, None)
        return True

    def button_down_segment(self, bb, beat, voice, seg_index, spacing, x, y, button):
        if self.split is not None:
            a, b = self.split
            if b is None:
                voice.segments.append(entities.VoiceSegment([], a * 4))
            else:
                n1 = list(voice.segments[self.split_index].notes)
                n2 = list(voice.segments[self.split_index].notes)
                self.document.track.voices[0].segments[self.split_index:self.split_index+1] = [
                    entities.VoiceSegment(n1, a * 4),
                    entities.VoiceSegment(n2, b * 4),
                ]
            self.primed = False
            return True
        return False

    def draw(self, ctx, hit):
        if not self.primed:
            return
        ctx.set_source_rgba(1,1,1,1)
        ctx.rectangle(self.x, self.y, self.width, self.height)
        ctx.fill()
        ctx.set_source_rgba(0,0,0,1)
        ctx.rectangle(self.x, self.y, self.width, self.height)
        ctx.stroke()
        ctx.set_source_rgba(0.7,0.7,0.7,1)
        ctx.move_to(self.x + self.width * self.split_point, self.y)
        ctx.line_to(self.x + self.width * self.split_point, self.y + self.height)
        ctx.stroke()

        ctx.set_source_rgba(0,0,0,1)
        if self.split is not None:
            a, b = self.split
        
            tab = {
                Fraction(2,1): chr(119132),
                Fraction(1,1): chr(119133),
                Fraction(1,2): chr(119134),
                Fraction(1,4): chr(119135),
                Fraction(1,8): chr(119136),
                Fraction(1,16): chr(119137),
                Fraction(1,32): chr(119138),
                Fraction(1,64): chr(119139),
                Fraction(1,128): chr(119140),
            }

            ctx.set_font_size(25)
            base, dots, triplet = resolution.categorize_note_duration(a)
            ctx.move_to(self.x + 5, self.level)
            if base > 2:
                text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
            else:
                text = tab[base] + '.'*dots
            ctx.show_text(text)
            ctx.set_font_size(12)
            ctx.move_to(self.x + 5, self.level + 12)
            ctx.show_text('3'*int(triplet))
            ctx.set_font_size(25)
            if b is not None:
                base, dots, triplet = resolution.categorize_note_duration(b)
                if base > 2:
                    text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                else:
                    text = tab[base] + '.'*dots
                ex = ctx.text_extents(text)
                ctx.move_to(self.x + self.width - 5 - ex.width, self.level)
                ctx.show_text(text)
                ctx.set_font_size(12)
                ctx.move_to(self.x + self.width - 5 - ex.width, self.level + 12)
                ctx.show_text('3'*int(triplet))

class StaffView:
    __slots__ = [
        'staff',
        'blocks',
        'reference',
        'left_margin',
        'highest_beat',
        'y',
        'height'
    ]
    def __init__(self, staff, y):
        assert isinstance(staff, entities.Staff)
        self.staff = staff
        self.blocks = entities.smear(staff.blocks)
        self.highest_beat = 0.0
        self.y = y

    def by_beat(self, beat):
        return entities.by_beat(self.blocks, beat)

    def raw_by_beat(self, beat):
        return entities.by_beat(self.staff.blocks, beat)

    def graph_point(self, index):
        return self.reference - (index - self.staff.bot*12)*5

    def note_position(self, beat, position):
        clef = self.by_beat(beat).clef
        return self.reference - (position - self.staff.bot*12 - clef)*5


if __name__=='__main__':
    Editor().ui()
