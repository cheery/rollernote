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
import random
import components
import subprocess
from fractions import Fraction

def get_tempo_envelope(document):
    default = random.randint(10, 200)
    for graph in document.track.graphs:
        if isinstance(graph, entities.Envelope) and graph.kind == 'tempo':
            env = resolution.linear_envelope(graph.segments, default)
            if env.check_positiveness():
                return env
    return resolution.LinearEnvelope([ (0, default, 0) ])

e_dialog_open = object()
e_document_change = object()

@gui.composable
def vu_meter(vol):
    comp = gui.current_composition.get()
    def to_scaler(v):
        if v > 0:
            dbfs = 20 * math.log10(v)
            return min(1.0, max(0.0, 1 - (dbfs / -96)))
        else:
            return 0.0
    this = gui.lazybundle(
        vol0 = 0.0,
        vol1 = 0.0,
        clip0 = False,
        clip1 = False
    )

    @gui.drawing
    def _draw_(ui, comp):
        bb = comp.shape
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        bb.trace(ctx)
        ctx.fill()
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        h0 = to_scaler(this.vol0) * (bb.height - 10)
        ctx.rectangle(bb.x+1, bb.y+bb.height - h0,
                      bb.width // 2 - 2, h0)
        ctx.fill()
        h1 = to_scaler(this.vol1) * (bb.height - 10)
        ctx.rectangle(bb.x+bb.width//2+1, bb.y+bb.height - h1, 8, h1)
        ctx.fill()
        ctx.set_source_rgba(1.0, 0.0, 0.0, 1.0)
        if this.clip0:
            ctx.rectangle(bb.x, bb.y, bb.width//2, 10)
        if this.clip1:
            ctx.rectangle(bb.x+bb.width//2, bb.y, bb.width//2, 10)
        ctx.fill()

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        if 0 <= y - comp.shape.y < 10:
            vol.clipping0 = False
            vol.clipping1 = False

    @gui.listen(gui.e_update)
    def _update_():
        this.vol0 = vol.volume0
        this.vol1 = vol.volume1
        this.clip0 = vol.clipping0
        this.clip1 = vol.clipping1

@gui.composable
def app(editor): 
    gui.workspace(color=(1,1,1,1), font_family='FreeSerif')
    this = gui.lazybundle(
        status = "program started",
        tool = plot_tool,
        looping = False,
        instrument_uid = None,
        dialog = None,
        dialog_args = [],
    )

    meter = vu_meter(editor.transport.volume_meter)
    meter.shape = gui.Box(10, 10, 20, 90)

    @gui.sub
    def toolbar1():
        gui.layout(gui.StaticLayout())
        gui.shape(gui.Box(40, 10, 500, 32))

        @gui.drawing
        def _set_clip_(ui, comp):
            ui.ctx.save()
            comp.shape.trace(ui.ctx)
            ui.ctx.clip()
        @gui.post_drawing
        def _clear_clip_(ui, comp):
            ui.ctx.restore()

        #@gui.row()
        @gui.sub
        def _row_():
            that = gui.lazybundle(scroll_x = 0)
            scroller = gui.ScrollableLayout(gui.RowLayout(), flexible_width = True, flexible_height = True)
            scroller.scroll_x = that.scroll_x
            scroller.scale_x = 1.0
            scroller.scale_y = 1.0
            gui.layout(scroller)
            @gui.listen(gui.e_update)
            def _update_():
                that.scroll_x = math.sin(editor.time) * 150 + 150
            new = components.button2("new", font_size=32, flexible_height = True)
            @new.listen(gui.e_button_down)
            def _new_down_(x, y, button):
                # TODO: Also clean up audio params!
                sdl2.SDL_PauseAudio(1)
                for plugin in editor.transport.plugins.values():
                    plugin.close()
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
                        voices = []
                    ),
                    instruments = [],
                    next_uid = entities.UidGenerator(300),
                )
                editor.transport.plugins = {}
                editor.transport.live_voices.clear()
                sdl2.SDL_PauseAudio(0)
            gui.hspacing(5)
            save = components.button2("save", font_size=32, flexible_height=True)
            @save.listen(gui.e_button_down)
            def _save_down_(x, y, button):
                document.store_plugins(editor.transport.plugins)
                entities.save_document('document.mide.zip', editor.document)
            gui.hspacing(5)
            # Editor history
            history = editor.history
            undo = components.button2(chr(0x21B6), font_size=24, disabled=len(history.undo_stack) == 0, flexible_height = True)
            @undo.listen(gui.e_motion)
            def _undo_status_(x, y):
                if len(history.undo_stack) > 0:
                    this.status = f"undo: {history.undo_stack[-1].name}"
            @undo.listen(gui.e_button_down)
            def _undo_down_(x, y, button):
                if len(history.undo_stack) > 0:
                    this.status = f"undone: {history.undo_stack[-1].name}"
                    history.undo()
                    undo.set_dirty()
                    redo.set_dirty()
            gui.hspacing(5)
            redo = components.button2(chr(0x21B7), font_size=24, disabled=len(history.redo_stack) == 0, flexible_height = True)
            @redo.listen(gui.e_motion)
            def _redo_status_(x, y):
                if len(history.redo_stack) > 0:
                    this.status = f"redo: {history.redo_stack[-1].name}"
            @redo.listen(gui.e_button_down)
            def _redo_down_(x, y, button):
                if len(history.redo_stack) > 0:
                    this.status = f"redone: {history.redo_stack[-1].name}"
                    history.redo()
                    undo.set_dirty()
                    redo.set_dirty()

    @gui.sub
    def toolbar2():
        gui.layout(gui.StaticLayout())
        gui.shape(gui.Box(40, 52, 500, 48))

        @gui.row()
        def _row_():
            looper = components.button2('loop=on' if this.looping else 'loop=off', font_size=16, flexible_height=True, min_width = 96)
            @looper.listen(gui.e_button_down)
            def _looper_down_(x, y, button):
                this.looping = not this.looping
                editor.transport.loop = this.looping
            gui.hspacing(5)
            record = components.button2('wav', font_size=16, flexible_height=True)
            @record.listen(gui.e_button_down)
            def _record_down_(x, y, button):
                # TODO: Open a dialog
                document.store_plugins(editor.transport.plugins)
                transport = audio.Transport(document.init_plugins(editor.pluginhost), document.mutes)
                bpm = get_tempo_envelope(editor.document)
                transport.play(bpm, editor.document.track.voices,
                    dict((s.uid, s) for s in editor.document.track.graphs))
                output = audio.WAVOutput(transport, 'temp.wav')
                while not transport.is_idle():
                    output.write_frame()
                output.close()
                for plugin in transport.plugins.values():
                    plugin.close()
                #subprocess.run(["ffmpeg", "-i", "-nostdin", "temp.wav", "temp.mp3"])
            gui.hspacing(5)
            play = components.button2(chr(0x25B6), font_size=32, flexible_height=True)
            @play.listen(gui.e_button_down)
            def _play_down_(x, y, button):
                if button == 1:
                    bpm = get_tempo_envelope(editor.document)
                    editor.transport.play(bpm, editor.document.track.voices,
                        dict((s.uid, s) for s in editor.document.track.graphs))
                if button == 3:
                    this.tool = transport_tool
            gui.hspacing(5)
            splitbutton = components.button2("split", font_size=32, flexible_height=True)
            @splitbutton.listen(gui.e_button_down)
            def _splitbutton_down_(x, y, button):
                this.tool = split_tool
            gui.hspacing(5)
            plotbutton = components.button2("plot", font_size=32, flexible_height=True)
            @plotbutton.listen(gui.e_button_down)
            def _plotbutton_down_(x, y, button):
                this.tool = plot_tool
            gui.hspacing(5)
            inputbutton = components.button2("input", font_size=32, flexible_height=True)
            @inputbutton.listen(gui.e_button_down)
            def _inputbutton_down_(x, y, button):
                this.tool = input_tool

    def instrument_button(x, y, instrument):
        plugin = editor.transport.plugins[instrument.uid]
        label = f"{instrument.uid}: {plugin.name}"
        openplugin = components.button(label, font_size=10)
        openplugin.shape = gui.Box(x, y, 80, 15)
        @openplugin.listen(gui.e_button_down)
        def _openplugin_down_(x, y, button):
            if plugin.widget is None:
                editor.widget(label, 120, 70, lv2.UIPayload, plugin)

        selected = instrument.uid == this.instrument_uid
        select = components.button("X" if selected else "", font_size=10, disabled=selected)
        select.shape = gui.Box(x+80, y, 15, 15)
        @select.listen(gui.e_button_down)
        def _select_down_(x, y, button):
            if button == 1:
                this.instrument_uid = instrument.uid
            if button == 2:
                mute = editor.document.mutes.get(instrument.uid, 0)
                if mute == -1:
                    editor.document.mutes.pop(instrument.uid, None)
                else:
                    editor.document.mutes[instrument.uid] = -1
            if button == 3:
                mute = editor.document.mutes.get(instrument.uid, 0)
                if mute == 1:
                    editor.document.mutes.pop(instrument.uid, None)
                else:
                    editor.document.mutes[instrument.uid] = 1
            select.set_dirty()

    for i, instrument in enumerate(editor.document.instruments):
        instrument_button(500 + 120*(i//7), 10 + (i%7)*20, instrument)
    @gui.drawing
    def _draw_instrument_colors_(ui, comp):
        for i, instrument in enumerate(editor.document.instruments):
            ui.ctx.set_source_rgba(*resolution.golden_ratio_color_varying(i))
            ui.ctx.rectangle(490 + 120*(i//7), 9 + (i%7)*20, 10, 17)
            ui.ctx.fill()
            mute = editor.document.mutes.get(instrument.uid, 0)
            if mute < 0:
                ui.ctx.set_source_rgba(0,0,0,1)
                ui.ctx.set_font_size(20)
                ui.ctx.move_to(490 - 5 + 120*(i//7), 9 + (i%7)*20 + 16)
                ui.ctx.show_text('S')
            elif mute > 0:
                ui.ctx.set_source_rgba(0,0,0,1)
                ui.ctx.set_font_size(20)
                ui.ctx.move_to(490 - 5 + 120*(i//7), 9 + (i%7)*20 + 16)
                ui.ctx.show_text('M')

    def add_instrument(x, y, uri, name):
        label = f"+ {name}"
        new_instrument = components.button(label, font_size=10)
        new_instrument.shape = gui.Box(x, y, 80, 15)
        @new_instrument.listen(gui.e_button_down)
        def _new_instrument_down_(x, y, button):
            sdl2.SDL_PauseAudio(1)
            uid = editor.document.next_uid()
            editor.document.instruments.append(entities.Instrument(uri, {}, {}, uid))
            plugin = editor.pluginhost.plugin(uri)
            editor.transport.plugins[uid] = plugin
            new_instrument.set_dirty()
            sdl2.SDL_PauseAudio(0)
    for i, (uri, name) in enumerate(editor.pluginhost.list_instrument_plugins()):
        add_instrument(1200 - 90, 10 + i*20, uri, name)

    document = editor.document

    icolors = {}
    for i, instrument in enumerate(document.instruments):
        icolors[instrument.uid] = resolution.golden_ratio_color_varying(i)

    layouts = {}
    y_base = 150
    for graph in document.track.graphs:
        if isinstance(graph, entities.Staff):
            layouts[graph.uid] = layout = StaffLayout(y_base, graph, document.track.voices)
        elif isinstance(graph, entities.ChordProgression):
            layouts[graph.uid] = layout = ChordProgressionLayout(y_base, graph)
        elif isinstance(graph, entities.Envelope):
            layouts[graph.uid] = layout = EnvelopeLayout(y_base, graph)
        else:
            assert False
        y_base += layout.height + 10
    beatline(editor, layouts, document.track, this.tool, this.instrument_uid, icolors)

    widget = gui.ui.get().widget

    add_staff = components.button("add staff")
    add_staff.shape = gui.Box(10, widget.height - 40, 96, 20)
    @add_staff.listen(gui.e_button_down)
    def _add_staff_(x,y,button):
        editor.document.track.graphs.append(
                    entities.Staff(editor.document.next_uid(), 3, 2, [
                        entities.StaffBlock(
                            beat = 0,
                            beats_in_measure = random.choice([3,4]),
                            beat_unit = 4,
                            canonical_key = random.randrange(-7, 8),
                            clef = 3,
                            mode = None
                        )
                    ]))

    add_cp = components.button("add chord prog.")
    add_cp.shape = gui.Box(116, widget.height - 40, 128, 20)
    @add_cp.listen(gui.e_button_down)
    def _add_cp_(x,y,button):
        editor.document.track.graphs.append(
            entities.ChordProgression(editor.document.next_uid(), []))

    add_e = components.button("add envelope")
    add_e.shape = gui.Box(254, widget.height - 40, 128, 20)
    @add_e.listen(gui.e_button_down)
    def _add_e_(x,y,button):
        editor.document.track.graphs.append(
            entities.Envelope(editor.document.next_uid(), "", []))

    components.label(this.status, 0, widget.height - 3)

    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        if repeat == 0:
            pass
            #@editor.plugin.event
            #def _event_():
            #    pass # TODO: fix
                #buf = editor.plugin.inputs['In']
                #editor.plugin.push_midi_event(buf, [0x91, key % 128, 0xFF])

    @gui.listen(gui.e_key_up)
    def _up_(key, modifier):
        pass
        #@editor.plugin.event
        #def _event_():
        #    pass # TODO: fix
            #buf = editor.plugin.inputs['In']
            #editor.plugin.push_midi_event(buf, [0x81, key % 128, 0xFF])

    if this.dialog is not None:
        this.dialog(editor, *this.dialog_args)

    @gui.listen(e_dialog_open)
    def _dialog_open_(dialog, args):
        this.dialog = dialog
        this.dialog_args = args

    @gui.listen(components.e_dialog_leave)
    def _dialog_leave_():
        this.dialog = None
        this.dialog_args = []

class StaffLayout:
    def __init__(self, y, staff, voices):
        assert isinstance(staff, entities.Staff)
        self.y = y
        self.staff = staff
        self.smeared = smeared = entities.smear(staff.blocks)
        self.last_beat = 0.0
        lowest = highest = 0
        for voice in voices:
            if voice.staff_uid == staff.uid:
                beat = 0.0
                for seg in voice.segments:
                    block = entities.by_beat(smeared, beat)
                    for note in seg.notes:
                        pitch = note.pitch
                        offset = pitch.position - staff.bot*12 - block.clef
                        lowest = min(lowest, offset)
                        highest = max(highest, offset)
                    beat += float(seg.duration)
                self.last_beat = max(self.last_beat, beat)
        self.margin_bot = staff.bot + min((lowest) // 12, 0)
        self.margin_top = max(staff.top, staff.bot + ((highest+9) // 12))
        self.span = (self.margin_top - self.margin_bot)*12+4
        self.height = self.span * 5
        self.start = (self.margin_top - staff.top)*12+2
        self.stop = (self.margin_top - staff.bot)*12+2
        self.reference = (self.stop+1) * 5 + self.y

        # Layout calculation begins
        margin = 35
        block = self.by_beat(0.0)
        if block.clef is not None:
            margin += 50
        if block.canonical_key is not None:
            canon_key = block.canonical_key
            margin += abs(canon_key) * 7
        #if block.beats_in_measure is not None or block.beat_unit is not None:
        #    pass
        margin += 30
        self.left_margin = margin

    def by_beat(self, beat):
        return entities.by_beat(self.smeared, beat)

    def raw_by_beat(self, beat):
        return entities.by_beat(self.staff.blocks, beat)

    def graph_point(self, index):
        return self.reference - (index - self.staff.bot*12)*5

    def note_position(self, beat, position):
        clef = self.by_beat(beat).clef
        return self.reference - (position - self.staff.bot*12 - clef)*5

    def block_width(self, block):
        width = 0
        if block.clef is not None:
            width += 50
        if block.canonical_key is not None:
            canon_key = block.canonical_key
            width += abs(canon_key) * 7
        if block.beats_in_measure is not None or block.beat_unit is not None:
            width += 30
        return width

class ChordProgressionLayout:
    def __init__(self, y, cp):
        self.y = y
        self.height = 20
        self.cp = cp
        self.last_beat = sum(float(seg.duration) for seg in cp.segments)

class EnvelopeLayout:
    def __init__(self, y, envelope):
        self.y = y
        self.height = 20
        self.envelope = envelope
        self.last_beat = sum(float(seg.duration) for seg in envelope.segments)
       
@gui.composable
def beatline(editor, layouts, track, tool_app, instrument_uid, icolors):
    widget = gui.ui.get().widget
    gui.shape(gui.Box(0, 150, widget.width, widget.height - 170))
    this = gui.lazybundle(
        scroll_x_anchor = None,
        scroll_x = 0,
        scroll_y_anchor = None,
        scroll_y = 0,
        scaling = False,
        scaling_factor = 1.0,
        beatballs = [],
    )

    @gui.listen(gui.e_update)
    def _update_():
        beatballs = []
        for voice in list(editor.transport.live_voices):
            if voice.next_vseg > voice.last_vseg:
                t = (editor.time - voice.last_vseg) / (voice.next_vseg - voice.last_vseg)
            else:
                t = 0
            x0 = monotonic_interpolation(voice.last_beat, beats, offsets, True)
            x1 = monotonic_interpolation(voice.beat, beats, offsets, True)
            beat = voice.last_beat*(1-t) + voice.beat*t
            x = x0*(1-t) + x1*t
            beatballs.append((beat, x))
        this.beatballs = beatballs

    # Scrolling behavior
    @gui.listen(gui.e_motion)
    @gui.listen(gui.e_dragging)
    def _motion_(x, y):
        if this.scroll_x_anchor is not None:
            this.scroll_x += (x - this.scroll_x_anchor) / this.scaling_factor
            this.scroll_x_anchor = x
        if this.scroll_y_anchor is not None:
            if this.scaling:
                this.scroll_x -= widget.width / 2 / this.scaling_factor
                this.scroll_y -= widget.height / 2 / this.scaling_factor
                this.scaling_factor += (y - this.scroll_y_anchor) * 0.01
                this.scroll_x += widget.width / 2 / this.scaling_factor
                this.scroll_y += widget.height / 2 / this.scaling_factor
            else:
                this.scroll_y += (y - this.scroll_y_anchor) / this.scaling_factor
            this.scroll_y_anchor = y

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        this.scroll_x_anchor = x
        this.scroll_y_anchor = y
        if button == 2:
            this.scroll_x -= widget.width / 2 / this.scaling_factor
            this.scroll_y -= widget.height / 2 / this.scaling_factor
            this.scaling_factor = 1.0
            this.scroll_x += widget.width / 2 / this.scaling_factor
            this.scroll_y += widget.height / 2 / this.scaling_factor
        this.scaling = (button == 3)

    @gui.listen(gui.e_button_up)
    def _up_(x, y, button):
        this.scroll_x_anchor = None
        this.scroll_y_anchor = None

    x0 = this.scroll_x + max(layout.left_margin for layout in layouts.values() if isinstance(layout, StaffLayout))

    for layout in layouts.values():
        layout.y += this.scroll_y
        if isinstance(layout, StaffLayout):
            layout.reference += this.scroll_y

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        comp.shape.trace(ctx)
        ctx.clip()
        ctx.scale(this.scaling_factor, this.scaling_factor)
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        envs = []
        for env in editor.document.track.graphs:
            if isinstance(env, entities.Envelope) and env.kind == 'dynamics':
                envs.append(env.uid)

        for layout in layouts.values():
            if isinstance(layout, ChordProgressionLayout):
                ctx.set_dash([4,2])
                ctx.move_to(0, layout.y+layout.height)
                ctx.line_to(ui.widget.width/this.scaling_factor, layout.y+layout.height)
                ctx.stroke()
                ctx.set_dash([])
                continue
            if isinstance(layout, EnvelopeLayout):
                ctx.set_dash([8,2])
                ctx.move_to(0, layout.y+layout.height)
                ctx.line_to(ui.widget.width/this.scaling_factor, layout.y+layout.height)
                ctx.stroke()
                ctx.set_dash([])
                ctx.move_to(this.scroll_x + 10, layout.y + layout.height)
                ctx.set_font_size(20)
                ctx.show_text(layout.envelope.kind)
                if layout.envelope.kind == 'dynamics':
                    i = envs.index(layout.envelope.uid)
                    color = resolution.golden_ratio_color_varying(i)
                    ctx.set_source_rgba(*color)
                    ctx.rectangle(x0 - 10, layout.y, 10, layout.height)
                    ctx.fill()
                continue
            # Staff lines
            # These are rendered without refering
            # to anything else but staff.top and staff.bot and margins
            for i in range(layout.start, layout.stop, 2):
                if i % 12 != 2:
                    k = i * 5
                    ctx.move_to(0, layout.y+k)
                    ctx.line_to(widget.width/this.scaling_factor, layout.y+k)
                    ctx.stroke()

            initial = layout.by_beat(0.0)
            canon_key = initial.canonical_key
            key = resolution.canon_key(canon_key)

            # Major/Minor letters above the 'clef'
            major = entities.Pitch(resolution.tonic(canon_key))
            minor = entities.Pitch(resolution.tonic(canon_key, 5))
            major_text = resolution.pitch_name(major, key, show_octave=False)
            minor_text = resolution.pitch_name(minor, key, show_octave=False)
            ctx.set_font_size(10)
            ctx.move_to(this.scroll_x + 35, layout.y + 9)
            ctx.show_text(f"{major_text} {minor_text}m")

            # Initial pitch markings
            ctx.set_font_size(10)
            clef = initial.clef
            for i in range(0, layout.span, 2):
                position = i + layout.margin_bot*12 + clef
                t = resolution.pitch_name(entities.Pitch(position), key)
                ctx.move_to(this.scroll_x + 10, layout.note_position(0.0, position)+4)
                ctx.show_text(t)

            for layout in layouts.values():
                if isinstance(layout, ChordProgressionLayout):
                    continue
                if isinstance(layout, EnvelopeLayout):
                    continue
                block = layout.by_beat(0.0)
                staff_block(ctx, layout, x0 - layout.left_margin + 35, block, block)
                # bar
                ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                ctx.move_to(x0, layout.graph_point(layout.staff.top*12 - 1))
                ctx.line_to(x0, layout.graph_point(layout.staff.bot*12 + 3))
                ctx.stroke()

                mute = editor.document.mutes.get(layout.staff.uid, 0)
                ctx.set_font_size(20)
                ctx.move_to(x0, layout.y + 20)
                ctx.show_text(['solo', '', 'mute'][mute+1])
                ctx.stroke()

            ctx.identity_matrix()
            ctx.reset_clip()
            for beat, x in this.beatballs:
                ctx.arc(x*this.scaling_factor, 150 - 25 * abs(math.sin(beat * math.pi)), 5, 0, 2*math.pi)
                ctx.stroke()
            comp.shape.trace(ctx)
            ctx.clip()
            ctx.scale(this.scaling_factor, this.scaling_factor)

    # Spacing configuration for note heads
    p = 20 # width of 1/128th beat note
    q = 50 # width of 1/1 beat note
    a = math.log(p / q) / math.log(1 / 128)

    # Computing positioning data for empty segments
    # from their empty neighbours
    def mean(xs):
        xs = list(xs)
        return sum(xs) // len(xs)
    empty_segment_position = {}
    for voice in track.voices:
        layout = layouts[voice.staff_uid]

        last_note_position = None
        rest_positions = []

        beat = 0
        for seg in voice.segments:
            if len(seg.notes) == 0:
                # Store empty segment for later processing
                rest_positions.append((beat, seg))
            else:
                note_position = mean(note.pitch.position for note in seg.notes)

                # Assign this position to previous empty segments
                for _, rest_seg in rest_positions:
                    if rest_seg not in empty_segment_position:
                        empty_segment_position[rest_seg] = []
                    if last_note_position is not None:
                        empty_segment_position[rest_seg].append(last_note_position)
                    empty_segment_position[rest_seg].append(note_position)

                # Clear list of rest positions
                rest_positions = []
                last_note_position = note_position
            beat += float(seg.duration)
        # If rest positions are left over, fill them using the last known note position
        for beat, rest_seg in rest_positions:
            if last_note_position is not None:
                if rest_seg not in empty_segment_position:
                    empty_segment_position[rest_seg] = []
                empty_segment_position[rest_seg].append(last_note_position)
    empty_segment_position = dict((seg, mean(positions)) for seg, positions in empty_segment_position.items())

    # Events on the line
    events = []
    E_ENVELOPE_SEGMENT = 4
    E_CHORD_PROGRESSION_SEGMENT = 3
    E_SEGMENT = 2
    E_BLOCK = 1
    E_BARLINE = 0
    def insert_event(beat, kind, value):
        bisect.insort_left(events, (beat, kind, value), key=lambda k: (k[0], k[1]))
    # Breaking segments into measures
    def beats_in_this_measure(layout, beat):
        this, future = entities.at_beat(layout.smeared, beat)
        if future is None:
            return this.beats_in_measure, False
        else:
            distance = future.beat - beat
            if distance < this.beats_in_measure:
                return distance, True
            else:
                return this.beats_in_measure, False
    for voice in track.voices:
        layout = layouts[voice.staff_uid]
        beat = 0.0
        remain, _ = beats_in_this_measure(layout, beat)
        for seg in voice.segments:
            duration = seg.duration
            while remain < duration:
                if remain > 0:
                    insert_event(beat, E_SEGMENT, (remain, seg, layout, voice))
                    duration -= remain
                    beat += float(remain)
                remain, _ = beats_in_this_measure(layout, beat)
            if duration != 0: # seg.duration <= remain
                insert_event(beat, E_SEGMENT, (duration, seg, layout, voice))
                remain -= duration
                beat += float(duration)
    def frange(start, stop, step):
        current = start
        while current < stop:
            yield current
            current += step
    # Inserting blocks into event stream
    for layout in layouts.values():
        if isinstance(layout, StaffLayout):
            previous = layout.smeared[0]
            for i, smear in enumerate(layout.smeared[1:], 1):
                for stop in frange(previous.beat + previous.beats_in_measure, smear.beat, previous.beats_in_measure):
                    insert_event(stop, E_BARLINE, layout)
                block = layout.staff.blocks[i]
                unusual = (smear.beat - previous.beat) % previous.beats_in_measure != 0
                insert_event(block.beat, E_BLOCK, (layout, block, smear, unusual))
                previous = smear
            for stop in frange(previous.beat + previous.beats_in_measure, layout.last_beat, previous.beats_in_measure):
                insert_event(stop, E_BARLINE, layout)
        elif isinstance(layout, ChordProgressionLayout):
            beat = 0.0
            for seg in layout.cp.segments:
                insert_event(beat, E_CHORD_PROGRESSION_SEGMENT, (layout, seg))
                beat += float(seg.duration)
        elif isinstance(layout, EnvelopeLayout):
            beat = 0.0
            for seg in layout.envelope.segments:
                insert_event(beat, E_ENVELOPE_SEGMENT, (layout, seg))
                beat += float(seg.duration)

    x = x0 + 20
    # Layout data to draw ties
    seg_xs = {}
    # Offsets and corresponding beat for drawing segment boxes/lines.
    offsets = [x]
    beats = [0.0]
    beat = 0.0
    push = [0, 0]
    push0 = 0 # Additional pushes from other items.
    push1 = 0

    barlines = []
    blocks = []
    segments = []
    envelope_segments = []
    chord_progression_segments = []

    trajectories = []
    for voice in track.voices:
        trajectories.append((voice.staff_uid, voice.uid, voice.dynamics_uid, [], []))

    last_beat = max((l.last_beat for l in layouts.values()), default=0.0)

    # "Efficient algorithms for music engraving,
    #  focusing on correctness"
    for time, which, value in events:
        if which == E_BLOCK and push0 > 0:
            x += push0
            push0 = 0
        if which in [E_SEGMENT, E_CHORD_PROGRESSION_SEGMENT, E_ENVELOPE_SEGMENT] and push0 + push1 > 0:
            x += push0 + push1
            push0 = push1 = 0
            offsets.append(x)
            beats.append(beat)
        if beat < time:
            # Since we may render polyrhythms, we need to do spacing by beat.
            x += q * (time - beat) ** a
            beat = time
            offsets.append(x)
            beats.append(beat)
        if which == E_BLOCK:
            layout, block, smear, unusual = value
            if unusual:
                y0 = layout.graph_point(layout.staff.top*12 - 1)
                y1 = layout.graph_point(layout.staff.bot*12 + 3)
                barlines.append((True, x, y0, y1))
                blocks.append((layout, x+10, block, smear))
                pushk = 20 + layout.block_width(block)
            else:
                blocks.append((layout, x, block, smear))
                pushk = 10 + layout.block_width(block)
            push1 = max(push1, pushk)
        if which == E_BARLINE:
            layout = value
            y0 = layout.graph_point(layout.staff.top*12 - 1)
            y1 = layout.graph_point(layout.staff.bot*12 + 3)
            barlines.append((False, x, y0, y1))
            push0 = 10
        if which == E_ENVELOPE_SEGMENT:
            layout, seg = value
            envelope_segments.append((beat, seg, layout, x))
        if which == E_CHORD_PROGRESSION_SEGMENT:
            layout, seg = value
            chord_progression_segments.append((beat, seg, layout, x))
        if which == E_SEGMENT:
            duration, seg, layout, voice = value
            tie = len(seg_xs.get(seg, []))
            segments.append((beat, x, tie, duration, seg, layout))
            if len(seg.notes) > 0:
                for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
                    if voice_uid == voice.uid:
                        p = mean(note.pitch.position for note in seg.notes)
                        y = layout.note_position(beat, p)
                        xs.append(x)
                        ys.append(y)
                    
            resolution.insert_in_list(seg_xs, seg, (beat, x))
    if beat < last_beat:
        x += q * (last_beat - beat) ** a
        offsets.append(x)
        beats.append(last_beat)
    for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
        if len(xs) == 0:
            xs.append(x0 + 20)
            ys.append(layout.y + layout.height // 2)
        

    @gui.drawing
    def _draw_lines_(ui, comp):
        ctx = ui.ctx
        #comp.shape.trace(ctx)
        #ctx.clip()
        for dashed, x, y0, y1 in barlines:
            if dashed:
                ctx.set_dash([4, 2])
            ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
            ctx.move_to(x, y0)
            ctx.line_to(x, y1)
            ctx.stroke()
            if dashed:
                ctx.set_dash([])

        for layout, x, block, smear in blocks:
            staff_block(ctx, layout, x+10, block, smear)

        envs = []
        for env in editor.document.track.graphs:
            if isinstance(env, entities.Envelope) and env.kind == 'dynamics':
                envs.append(env.uid)

        ctx.set_dash([4, 2])
        for _, voice_uid, dynamics_uid, xs, ys in trajectories:
            mute = editor.document.mutes.get(voice_uid, 0)
            color = [(1,1,0), (1,0,0), (0, 0, 0)][mute+1]
            ctx.set_source_rgb(*color)
            for i, (x,y) in enumerate(zip(xs, ys)):
                if i == 0:
                    ctx.move_to(x, y)
                else:
                    ctx.line_to(x, y)
            ctx.stroke()
        ctx.set_dash([])

        ctx.set_dash([8, 2])
        for _, voice_uid, dynamics_uid, xs, ys in trajectories:
            if dynamics_uid is not None:
                color = resolution.golden_ratio_color_varying(envs.index(dynamics_uid))
                ctx.set_source_rgba(*color)
                for i, (x,y) in enumerate(zip(xs, ys)):
                    if i == 0:
                        ctx.move_to(x, y - 3)
                    else:
                        ctx.line_to(x, y - 3)
                ctx.stroke()
        ctx.set_dash([])

        for beat, seg, layout, x0 in envelope_segments:
            ctx.set_source_rgba(0.7,0.7,0.7,1)
            ctx.move_to(x0, layout.y)
            ctx.line_to(x0, layout.y+layout.height)
            ctx.stroke()
            ctx.set_source_rgba(0,0,0,1)
            ctx.move_to(x0, layout.y+layout.height)
            x1 = monotonic_interpolation(beat + float(seg.duration), beats, offsets, False)
            if seg.control > 0:
                ctx.move_to(x0, layout.y+layout.height/2)
                ctx.line_to(x1, layout.y)
                ctx.move_to(x0, layout.y+layout.height/2)
                ctx.line_to(x1, layout.y+layout.height)
                ctx.stroke()
            elif seg.control < 0:
                ctx.move_to(x1, layout.y+layout.height/2)
                ctx.line_to(x0, layout.y)
                ctx.move_to(x1, layout.y+layout.height/2)
                ctx.line_to(x0, layout.y+layout.height)
                ctx.stroke()
            elif seg.value is not None:
                if layout.envelope.kind.endswith('dynamics'):
                    levs =  [ 0.0,  0.2,  0.3,  0.4,  0.6, 0.7,  0.9]
                    texts = ['__', 'pp',  'p', 'mp', 'mf', 'f', 'ff']
                    i = bisect.bisect_right(levs, seg.value)
                    ctx.show_text(texts[i-1])
                else:
                    ctx.show_text(str(seg.value))

        for beat, seg, layout, x0 in chord_progression_segments:
            ctx.set_source_rgba(0,0,0,1)
            ctx.move_to(x0, layout.y+layout.height)
            ctx.show_text(str(seg.nth))
            if editor.document.mutes.get(layout.cp.uid, 0) > 0:
                continue
            x1 = monotonic_interpolation(beat + float(seg.duration), beats, offsets, False)
            for staff in layouts.values():
                if isinstance(staff, StaffLayout):
                    block = staff.by_beat(beat)
                    if block.mode in ['minor', 'major']:
                        ton = resolution.tonic(block.canonical_key, {'minor': 5, 'major': 0}[block.mode])
                        low = staff.margin_bot*12 + block.clef
                        high = staff.margin_top*12 + block.clef
                        for pos in range(low, high+1):
                            win = False
                            if pos % 7 == (ton + seg.nth - 1) % 7:
                                win = True
                                ctx.set_source_rgba(0,0,1,0.2)
                            if pos % 7 == (ton + seg.nth + 1) % 7:
                                win = True
                                ctx.set_source_rgba(1,0,0,0.2)
                            if pos % 7 == (ton + seg.nth + 3) % 7:
                                win = True
                                ctx.set_source_rgba(0,1,0,0.2)
                            if win:
                                y = staff.note_position(beat, pos)
                                ctx.move_to(x0, y+2)
                                ctx.line_to(x1, y+2)
                                ctx.line_to(x1, y-2)
                                ctx.line_to(x0, y-2)
                                ctx.fill()

        for beat, x, tie, duration, seg, layout in segments:
            ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
            block = layout.by_beat(beat)
            beat_unit = block.beat_unit
            cat = resolution.categorize_note_duration(duration / beat_unit)
            if cat is None:
                if len(seg.notes) == 0:
                    t = empty_segment_position[seg]
                else:
                    t = mean(note.pitch.position for note in seg.notes)
                t = (t - t % 12) - 6
                y = layout.note_position(beat, t)
                ctx.set_font_size(10)
                ctx.move_to(x - 4, y -2)
                ctx.show_text(f'|{duration / beat_unit}|')
                d = resolution.quantize_fraction(duration / beat_unit)
                cat = resolution.categorize_note_duration(d)
            base, dots, triplet = cat
            if len(seg.notes) == 0:
                try:
                    t = empty_segment_position[seg]
                except KeyError:
                    t = (layout.staff.top*6 + layout.staff.bot*6) + block.clef + 1
                t = (t - t % 12) - 6
                y = layout.note_position(beat, t)
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
                    ctx.line_to(x + 5, y + 5)
                    ctx.line_to(x + 5, y - 5)
                    ctx.line_to(x, y)
                    ctx.stroke()
                for dot in range(dots):
                    ctx.arc(x + 16 + dot*5, y + 3, 2, 0, 2*math.pi)
                    ctx.fill()
            for note in seg.notes:
                    ctx.set_source_rgba(0,0,0,1)
                    pitch = note.pitch
                    y = layout.note_position(beat, pitch.position)
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
                    if tie > 0:
                        past, px = seg_xs[seg][tie-1]
                        y0 = layout.note_position(past, pitch.position)
                        ctx.move_to(px+8, y0 + 3)
                        ctx.curve_to(px+8, 8 + y0 + 3,
                                     x-8, 8 + y + 3,
                                     x-8, 0 + y + 3)
                        ctx.stroke()
                    ctx.set_source_rgba(*icolors.get(note.instrument_uid, (0.25,0.25,0.25,1.0)))
                    ctx.arc(x - 2, y + 2, 3, 0, 2*math.pi)
                    ctx.fill()
            ctx.set_source_rgba(0,0,0,1)
            if len(seg.notes) > 0:
                high = min(layout.note_position(beat, note.pitch.position) for note in seg.notes)
                low = max(layout.note_position(beat, note.pitch.position) for note in seg.notes)
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

    for graph_uid, layout in layouts.items():
        tool_app(
          editor,
          graph_uid,
          layout,
          seg_xs,
          offsets,
          beats,
          trajectories,
          track,
          instrument_uid,
          icolors,
          this.scaling_factor,
        )

        staff_app(editor, layout, x0, this.scaling_factor)

    comp = gui.current_composition.get()
    @gui.listen(e_document_change)
    def _document_change_():
        comp.set_dirty()

    def _draw_(ui, comp):
        ui.ctx.reset_clip()
        ui.ctx.identity_matrix()
    comp.post_drawings.append(_draw_)

@gui.composable
def staff_app(editor, layout, x0, scaling_factor):
    _ui = gui.ui.get()
    comp = gui.current_composition.get()
    gui.shape(gui.Box(0, layout.y * scaling_factor, x0 * scaling_factor, layout.height * scaling_factor))
    if isinstance(layout, ChordProgressionLayout):
        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            if button == 3:
                mute = editor.document.mutes.get(layout.cp.uid, 0)
                if mute == 1:
                    editor.document.mutes.pop(layout.cp.uid, None)
                else:
                    editor.document.mutes[layout.cp.uid] = 1
        return
    if isinstance(layout, EnvelopeLayout):
        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            if button == 1:
                _ui.custom_event(e_dialog_open, comp, envelope_dialog, [layout.envelope])
        return
    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        if button == 1:
            _ui.custom_event(e_dialog_open, comp, staff_dialog, [layout.staff])
        if button == 2:
            mute = editor.document.mutes.get(layout.staff.uid, 0)
            if mute == -1:
                editor.document.mutes.pop(layout.staff.uid, None)
            else:
                editor.document.mutes[layout.staff.uid] = -1
        if button == 3:
            mute = editor.document.mutes.get(layout.staff.uid, 0)
            if mute == 1:
                editor.document.mutes.pop(layout.staff.uid, None)
            else:
                editor.document.mutes[layout.staff.uid] = 1
        comp.set_dirty()

@gui.composable
def envelope_dialog(editor, envelope):
    with components.dialog():
        def change_kind(text):
            envelope.kind = text
            gui.broadcast(e_document_change)
        m = components.textbox(envelope.kind, change_kind)
        m.shape = gui.Box(358, 230, 32*2, 20)

        enabled = len(editor.document.track.graphs) > 1
        rm = components.button("remove envelope", disabled = not enabled)
        rm.shape = gui.Box(220, 400, 96, 20)
        @rm.listen(gui.e_button_down)
        def _rm_(x,y,button):
            if enabled:
                editor.document.track.graphs.remove(envelope)
                for voice in list(editor.document.track.voices):
                    if voice.dynamics_uid == envelope.uid:
                        voice.dynamics_uid = None
                gui.inform(components.e_dialog_leave, rm)

@gui.composable
def staff_dialog(editor, staff):
    with components.dialog():
        def changer(obj, attr, range=(0,100)):
            def _change_(text):
                try:
                    i = int(text.strip())
                    if range[0] <= i <= range[1]:
                        setattr(obj, attr, i)
                    gui.broadcast(e_document_change)
                except ValueError:
                    pass
            return _change_

        t = components.textbox(str(staff.top), changer(staff, 'top'))
        t.shape = gui.Box(200, 200, 64, 20)
        u = components.textbox(str(staff.bot), changer(staff, 'bot'))
        u.shape = gui.Box(200, 230, 64, 20)
        initial = staff.blocks[0]
        bm = components.textbox(str(initial.beats_in_measure),
                               changer(initial, 'beats_in_measure', (1,100)))
        bm.shape = gui.Box(274, 200, 32, 20)
        bu = components.textbox(str(initial.beat_unit),
                               changer(initial, 'beat_unit', (1,128)))
        bu.shape = gui.Box(274, 230, 32, 20)
        ck = components.textbox(str(initial.canonical_key),
                               changer(initial, 'canonical_key', (-7,+7)))
        ck.shape = gui.Box(316, 200, 32, 20)
        c = components.textbox(str(initial.clef),
                               changer(initial, 'clef', (-100, +100)))
        c.shape = gui.Box(316, 230, 32, 20)
        def change_mode(text):
            if text in ['major', 'minor']:
                initial.mode = text
                gui.broadcast(e_document_change)
            elif text == "":
                initial.mode = None
                gui.broadcast(e_document_change)
        m = components.textbox(str(initial.mode or ""), change_mode)
        m.shape = gui.Box(358, 230, 32*2, 20)

        enabled = len(editor.document.track.graphs) > 1
        rm_staff = components.button("remove staff", disabled = not enabled)
        rm_staff.shape = gui.Box(220, 400, 96, 20)
        @rm_staff.listen(gui.e_button_down)
        def _rm_staff_(x,y,button):
            if enabled:
                editor.document.track.graphs.remove(staff)
                for voice in list(editor.document.track.voices):
                    if voice.staff_uid == staff.uid:
                        editor.document.track.voices.remove(voice)
                gui.inform(components.e_dialog_leave, rm_staff)

def location_as_position(layout, offsets, beats, x, y):
    beat = monotonic_interpolation(x, offsets, beats)
    clef = entities.by_beat(layout.smeared, beat).clef
    return beat, round((layout.reference - y) / 5) + layout.staff.bot*12 + clef

def nearest_voice(trajectories, ix, iy, current_staff_uid):
    closest = None
    closest_y = None
    closest_z = None
    distance = None
    for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
        if current_staff_uid == staff_uid:
            y = monotonic_interpolation(ix, xs, ys)
            z = monotonic_interpolation(ix, xs, xs)
            d = (y - iy)**2 + (z - ix)**2
            if distance is None or d < distance:
                distance = d
                closest_y = y
                closest_z = z
                closest = voice_uid
    return closest, closest_z, closest_y

def get_segment(refbeat, track, voice_uid):
    for voice in track.voices:
        if voice.uid == voice_uid:
            beat = 0.0
            for seg in voice.segments:
                if 0 <= refbeat - beat < float(seg.duration):
                    return beat, seg
                beat += float(seg.duration)
    if beat <= refbeat:
        return beat, None

@gui.composable
def transport_tool(editor, staff_uid, layout, seg_xs, offsets, beats, trajectories, track, instrument_uid, icolors, sf):
    _ui = gui.ui.get()
    _comp = gui.current_composition.get()
    gui.shape(gui.Box(0, layout.y*sf, _ui.widget.width, layout.height*sf))
    if isinstance(layout, ChordProgressionLayout):
        return
    if isinstance(layout, EnvelopeLayout):
        return
    this = gui.lazybundle(
        mouse_x = 0,
        mouse_y = 0,
        beat = 0
    )
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        this.mouse_x = x / sf
        this.mouse_y = y / sf
        this.beat = round(monotonic_interpolation(x / sf, offsets, beats))

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        if button == 1:
            editor.transport.play_start = this.beat
        if button == 2:
            editor.transport.play_start = None
            editor.transport.play_end = None
        if button == 3:
            editor.transport.play_end = this.beat
        _comp.set_dirty()

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        x = monotonic_interpolation(this.beat, beats, offsets, True)
        ctx.set_source_rgba(1,0,0,1)
        ctx.move_to(x, layout.y)
        ctx.line_to(x, layout.y+layout.height)
        ctx.stroke()

        if editor.transport.play_start is not None:
            ctx.set_source_rgba(0,0,0,0.7)
            x0 = monotonic_interpolation(0.0, beats, offsets, True)
            x1 = monotonic_interpolation(editor.transport.play_start, beats, offsets, True)
            ctx.rectangle(x0, layout.y, x1 - x0, layout.height)
            ctx.fill()
        if editor.transport.play_end is not None:
            ctx.set_source_rgba(0,0,0,0.7)
            x2 = monotonic_interpolation(editor.transport.play_end, beats, offsets, True)
            x3 = monotonic_interpolation(layout.last_beat, beats, offsets, True)
            ctx.rectangle(x2, layout.y, x3 - x2, layout.height)
            ctx.fill()

@gui.composable
def plot_tool(editor, staff_uid, layout, seg_xs, offsets, beats, trajectories, track, instrument_uid, icolors, sf):
    _ui = gui.ui.get()
    _comp = gui.current_composition.get()
    gui.shape(gui.Box(0, layout.y*sf, _ui.widget.width, layout.height*sf))
    if isinstance(layout, ChordProgressionLayout):
        return
    if isinstance(layout, EnvelopeLayout):
        return

    voice_lock = gui.state(False)
    mouse_x = gui.state(0)
    mouse_y = gui.state(0)
    nearest = gui.state((None, None, None))
    beat_position = gui.state(None)
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        mouse_x.lazy(x / sf)
        mouse_y.lazy(y / sf)
        if not voice_lock.value:
            nearest.value = nearest_voice(trajectories, mouse_x.value, mouse_y.value, layout.staff.uid)
        for voice in track.voices:
            if voice.staff_uid != staff_uid and nearest.value[0] == voice.uid:
                nearest.value = (None, None, None)

        beat_position.value = location_as_position(
          layout, offsets, beats, mouse_x.value, mouse_y.value)

    @gui.listen(gui.e_key_down)
    def _keydown_(key, repeat, modifier):
        if nearest.value[0] is not None:
            if key == sdl2.SDLK_m:
                mute = editor.document.mutes.get(nearest.value[0], 0)
                if mute == 1:
                    editor.document.mutes.pop(nearest.value[0], None)
                else:
                    editor.document.mutes[nearest.value[0]] = 1
            if key == sdl2.SDLK_s:
                mute = editor.document.mutes.get(nearest.value[0], 0)
                if mute == -1:
                    editor.document.mutes.pop(nearest.value[0], None)
                else:
                    editor.document.mutes[nearest.value[0]] = -1
            if key == sdl2.SDLK_d:
                envs = []
                for env in editor.document.track.graphs:
                    if isinstance(env, entities.Envelope) and env.kind == 'dynamics':
                        envs.append(env.uid)
                for voice in editor.document.track.voices:
                    if voice.uid == nearest.value[0]:
                        if voice.dynamics_uid is None and len(envs) > 0:
                            voice.dynamics_uid = envs[0]
                        elif voice.dynamics_uid is not None:
                            i = envs.index(voice.dynamics_uid) + 1
                            if i < len(envs):
                                voice.dynamics_uid = envs[i]
                            else:
                                voice.dynamics_uid = None
                _comp.set_dirty()

    @gui.listen(gui.e_leaving)
    def _leaving_(x, y):
        nearest.value = (None, None, None)
        beat_position.value = None
        voice_lock.value = False

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        if beat_position.value and nearest.value[0] is not None:
            refbeat, position = beat_position.value
            _, seg = get_segment(refbeat, track, nearest.value[0])
            if button == 1 and seg is not None:
                if not any(note.pitch.position == position for note in seg.notes):
                    seg.notes.append(entities.Note(
                        entities.Pitch(position),
                        instrument_uid))
                    _comp.set_dirty()
                    beat_position.value = None
            if button == 2 and seg is not None:
                for note in seg.notes:
                    if note.pitch.position == position:
                        seg.notes.remove(note)
                        _comp.set_dirty()
                        beat_position.value = None
                        break
            if button == 3:
                voice_lock.value = not voice_lock.value

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        if voice_lock.value:
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
        for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
            if nearest.value[0] == voice_uid:
                for i, (x,y) in enumerate(zip(xs, ys)):
                    if i == 0:
                        ctx.move_to(x, y)
                    else:
                        ctx.line_to(x, y)
                ctx.stroke()
        if beat_position.value:
            ctx.set_source_rgba(*icolors.get(instrument_uid, (0.25,0.25,0.25,1.0)))
            beat, position = beat_position.value
            x = mouse_x.value
            y = layout.note_position(beat, position)
            ctx.arc(x, y, 5, 0, 2*math.pi)
            ctx.fill()

@gui.composable
def split_tool(editor, staff_uid, layout, seg_xs, offsets, beats, trajectories, track, instrument_uid, icolors, sf):
    _ui = gui.ui.get()
    gui.shape(gui.Box(0, layout.y*sf, _ui.widget.width, layout.height*sf))

    if isinstance(layout, ChordProgressionLayout):
        return
    if isinstance(layout, EnvelopeLayout):
        return

    voice_lock = gui.state(False)
    mouse_x = gui.state(0)
    mouse_y = gui.state(0)
    nearest = gui.state((None, None, None))
    bseg = gui.state((0.0, None, 0, 0))
    beat_position = gui.state(None)
    bu_split = gui.state(None)
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        mouse_x.lazy(x / sf)
        mouse_y.lazy(y / sf)
        if not voice_lock.value:
            nearest.value = nearest_voice(trajectories, mouse_x.value, mouse_y.value, layout.staff.uid)
        for voice in track.voices:
            if voice.staff_uid != staff_uid and nearest.value[0] == voice.uid:
                nearest.value = (None, None, None)

        beat_position.value = location_as_position(
          layout, offsets, beats, mouse_x.value, mouse_y.value)

        x1 = offsets[0]
        for voice in track.voices:
            if voice.uid == nearest.value[0]:
                beat = 0.0
                for seg in voice.segments:
                    x0 = monotonic_interpolation(beat, beats, offsets, True)
                    x1 = monotonic_interpolation(beat + float(seg.duration), beats, offsets, True)
                    if x0 < mouse_x.value <= x1:
                        bseg.value = beat, seg, x0, x1
                    beat += float(seg.duration)
                if x1 <= mouse_x.value:
                    bseg.value = beat, None, x1, _ui.widget.width
        if bseg.value[2] < bseg.value[3]:
           if bseg.value[1] is not None:
               t = (mouse_x.value - bseg.value[2]) / (bseg.value[3] - bseg.value[2])
               bu = layout.by_beat(bseg.value[0]).beat_unit
               total = bseg.value[1].duration / bu
               a = resolution.quantize_fraction(t * float(total))
               b = total - a
               if b in resolution.generate_all_note_durations():
                   bu_split.value = (bu, a, b, bseg.value[1])
           else:
               bu = layout.by_beat(bseg.value[0]).beat_unit
               a = resolution.quantize_fraction((mouse_x.value - bseg.value[2]) / 50)
               bu_split.value = (bu, a, None, None)

    @gui.listen(gui.e_leaving)
    def _leaving_(x, y):
        nearest.value = (None, None, None)
        bseg.value = (0, None, 0, 0)
        beat_position.value = None
        voice_lock.value = False

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        if beat_position.value and nearest.value[0] is not None:
            refbeat, position = beat_position.value
            if button == 3:
                voice_lock.value = not voice_lock.value
            if button == 1 and bu_split.value is not None and bu_split.value[3] == bseg.value[1]:
                bu, a, b, seg = bu_split.value
                if b is None:
                    for voice in track.voices:
                        if voice.uid == nearest.value[0]:
                            voice.segments.append(entities.VoiceSegment([], a * bu))
                else:
                    for voice in track.voices:
                        if voice.uid == nearest.value[0]:
                            n1 = list(seg.notes)
                            n2 = list(seg.notes)
                            i = voice.segments.index(seg)
                            voice.segments[i:i+1] = [
                                entities.VoiceSegment(n1, a * bu),
                                entities.VoiceSegment(n2, b * bu),
                            ]
                _leaving_(x, y)
              

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        if voice_lock.value:
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
        for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
            if nearest.value[0] == voice_uid:
                for i, (x,y) in enumerate(zip(xs, ys)):
                    if i == 0:
                        ctx.move_to(x, y)
                    else:
                        ctx.line_to(x, y)
                ctx.stroke()
        if bseg.value[3] > bseg.value[2]:
            beat, seg, x0, x2 = bseg.value
            x1 = max(x0, mouse_x.value)
            for staff_uid, voice_uid, dynamics_uid, xs, ys in trajectories:
                if nearest.value[0] == voice_uid:
                     ctx.set_source_rgba(1.0, 0.0, 1.0, 0.75)
                     y0 = monotonic_interpolation(x0, xs, ys)
                     y1 = monotonic_interpolation(x1, xs, ys)
                     y2 = monotonic_interpolation(x2, xs, ys)
                     ctx.move_to(x0, y0 + 5)
                     ctx.line_to(x1, y1 + 5)
                     ctx.line_to(x1, y1 - 30)
                     ctx.line_to(x0, y0 - 30)
                     ctx.fill()
                     ctx.set_source_rgba(1.0, 1.0, 0.0, 0.75)
                     ctx.move_to(x1, y1 + 5)
                     ctx.line_to(x2, y2 + 5)
                     ctx.line_to(x2, y2 - 30)
                     ctx.line_to(x1, y1 - 30)
                     ctx.fill()
        if bu_split.value != None and bu_split.value[3] == bseg.value[1]:
            ctx.set_source_rgba(0,0,0,1)
            beat, seg, x0, x2 = bseg.value
            bu, a, b, seg = bu_split.value
            level = mouse_y.value
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
            cat = resolution.categorize_note_duration(a)
            if cat is not None:
                base, dots, triplet = cat
                ctx.move_to(x0 + 5, level)
                if base > 2:
                    text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                else:
                    text = tab[base] + '.'*dots
                ctx.show_text(text)
                ctx.set_font_size(12)
                ctx.move_to(x0 + 5, level + 12)
                ctx.show_text('3'*int(triplet))
                ctx.set_font_size(25)
                if b is not None:
                    base, dots, triplet = resolution.categorize_note_duration(b)
                    if base > 2:
                        text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                    else:
                        text = tab[base] + '.'*dots
                    ex = ctx.text_extents(text)
                    ctx.move_to(x2 - 5 - ex.width, level)
                    ctx.show_text(text)
                    ctx.set_font_size(12)
                    ctx.move_to(x2 - 5 - ex.width, level + 12)
                    ctx.show_text('3'*int(triplet))

@gui.composable
def input_tool(editor, staff_uid, layout, seg_xs, offsets, beats, trajectories, track, instrument_uid, icolors, sf):
    _ui = gui.ui.get()
    gui.shape(gui.Box(0, layout.y*sf, _ui.widget.width, layout.height*sf))
    if isinstance(layout, ChordProgressionLayout):
        this = gui.lazybundle(
            document = editor.document,
            seg_index = 0,
            beat = 0.0,
            base_note = Fraction(1, 4),
            dots = 0,
            tri = False,
        )
        if this.document != editor.document:
            this.seg_index = 0
            this.beat = 0
        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            if button == 1:
                beatpoint = monotonic_interpolation(x / sf, offsets, beats)
                beat = 0.0
                i = 0
                for seg in layout.cp.segments:
                    if beatpoint < beat + float(seg.duration) / 2:
                        break
                    beat += float(seg.duration)
                    i += 1
                this.beat = beat
                this.seg_index = i
        @gui.listen(gui.e_key_down)
        def _down_(key, repeat, modifier):
            if key == sdl2.SDLK_a:
                this.base_note /= 2
            if key == sdl2.SDLK_w:
                this.base_note *= 2
            if key == sdl2.SDLK_z and this.dots > 0:
                this.dots -= 1
            if key == sdl2.SDLK_x:
                this.dots += 1
            if key == sdl2.SDLK_e:
                this.tri = not this.tri
            if key == sdl2.SDLK_BACKSPACE:
                if this.seg_index > 0:
                    seg = layout.cp.segments[this.seg_index-1]
                    layout.cp.segments[this.seg_index-1:this.seg_index] = []
                    this.seg_index -= 1
                    this.beat -= float(seg.duration)
                    this._composition.set_dirty()
            nth = None
            duration = resolution.build_note_duration(this.base_note, this.dots, this.tri) * 4
            if key == sdl2.SDLK_1:
                nth = 1
            if key == sdl2.SDLK_2:
                nth = 2
            if key == sdl2.SDLK_3:
                nth = 3
            if key == sdl2.SDLK_4:
                nth = 4
            if key == sdl2.SDLK_5:
                nth = 5
            if key == sdl2.SDLK_6:
                nth = 6
            if key == sdl2.SDLK_7:
                nth = 7
            if nth is not None:
                seg = entities.ChordProgressionSegment(nth, duration)
                layout.cp.segments[this.seg_index:this.seg_index] = [seg]
                this.seg_index += 1
                this.beat += float(seg.duration)
                this._composition.set_dirty()
            if key == sdl2.SDLK_LEFT:
                if this.seg_index > 0:
                    this.seg_index -= 1
                    this.beat -= float(layout.cp.segments[this.seg_index].duration)
            if key == sdl2.SDLK_RIGHT:
                if this.seg_index and this.seg_index < len(layout.cp.segments):
                    this.beat += float(layout.cp.segments[this.seg_index].duration)
                    this.seg_index += 1

        @gui.drawing
        def _draw_(ui, comp):
            ctx = ui.ctx
            if ui.focus == comp.key:
                x = monotonic_interpolation(this.beat, beats, offsets, True)
                ctx.move_to(x,layout.y)
                ctx.line_to(x,layout.y+layout.height)
                ctx.stroke()

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
                if True:
                    base, dots, triplet = this.base_note, this.dots, this.tri
                    if triplet:
                        dots = 0
                    ctx.move_to(x + 15, layout.y - 10)
                    if base > 2:
                        text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                    else:
                        text = tab[base] + '.'*dots
                    ctx.show_text(text)
                    ctx.set_font_size(12)
                    ctx.move_to(x + 15, layout.y + 2)
                    ctx.show_text('3'*int(triplet))
                    ctx.set_font_size(25)

        return
    if isinstance(layout, EnvelopeLayout):
        this = gui.lazybundle(
            document = editor.document,
            seg_index = 0,
            beat = 0.0,
            base_note = Fraction(1, 4),
            dots = 0,
            tri = False,
            tapped = random.randint(10, 200),
            taps = [],
        )
        if this.document != editor.document:
            this.seg_index = 0
            this.beat = 0
            this.tapped = random.randint(10, 200)
            this.taps = []
        @gui.listen(gui.e_button_down)
        def _button_down_(x, y, button):
            if button == 1:
                beatpoint = monotonic_interpolation(x / sf, offsets, beats)
                beat = 0.0
                i = 0
                for seg in layout.envelope.segments:
                    if beatpoint < beat + float(seg.duration) / 2:
                        break
                    beat += float(seg.duration)
                    i += 1
                this.beat = beat
                this.seg_index = i
        @gui.listen(gui.e_text)
        def _text_(text):
            control = None
            value = None
            if text == '<':
                control = +1
            if text == '>':
                control = -1
            if text == '0':
                control = 0
                value = None
            if layout.envelope.kind.endswith('dynamics'):
                if text == '1':
                    control = 0
                    value = 0.2 # pp
                if text == '2':
                    control = 0
                    value = 0.3 # p
                if text == '3':
                    control = 0
                    value = 0.4 # mp
                if text == '4':
                    control = 0
                    value = 0.6 # mf
                if text == '5':
                    control = 0
                    value = 0.7 # f
                if text == '6':
                    control = 0
                    value = 0.9 # ff
            if layout.envelope.kind.endswith('tempo'):
                if text == '1':
                    control = 0
                    value = 40
                if text == '2':
                    control = 0
                    value = 50
                if text == '3':
                    control = 0
                    value = 60
                if text == '4':
                    control = 0
                    value = 70
                if text == '5':
                    control = 0
                    value = 80
                if text == '6':
                    control = 0
                    value = 90
                if text == '7':
                    control = 0
                    value = 100
                if text == '8':
                    control = 0
                    value = 110
                if text == '9':
                    control = 0
                    value = 120
                if text == 't':
                    control = 0
                    value = this.tapped
            duration = resolution.build_note_duration(this.base_note, this.dots, this.tri) * 4
            if control is not None:
                seg = entities.EnvelopeSegment(control, value, duration)
                layout.envelope.segments[this.seg_index:this.seg_index] = [seg]
                this.seg_index += 1
                this.beat += float(seg.duration)
                this._composition.set_dirty()
        @gui.listen(gui.e_key_down)
        def _down_(key, repeat, modifier):
            if key == sdl2.SDLK_q and repeat == 0:
                this.taps.append(editor.time)
                this.taps = this.taps[-3:]
                tiptap = 0.0
                for i in range(len(this.taps)-1):
                    begin = this.taps[i]
                    end = this.taps[i+1]
                    tiptap += end - begin
                if tiptap > 0 and len(this.taps) > 1:
                    tiptap /= len(this.taps)-1
                    this.tapped = round(60 / tiptap)
            if key == sdl2.SDLK_a:
                this.base_note /= 2
            if key == sdl2.SDLK_w:
                this.base_note *= 2
            if key == sdl2.SDLK_z and this.dots > 0:
                this.dots -= 1
            if key == sdl2.SDLK_x:
                this.dots += 1
            if key == sdl2.SDLK_e:
                this.tri = not this.tri
            if key == sdl2.SDLK_BACKSPACE:
                if this.seg_index > 0:
                    seg = layout.envelope.segments[this.seg_index-1]
                    layout.envelope.segments[this.seg_index-1:this.seg_index] = []
                    this.seg_index -= 1
                    this.beat -= float(seg.duration)
                    this._composition.set_dirty()
            if key == sdl2.SDLK_LEFT:
                if this.seg_index > 0:
                    this.seg_index -= 1
                    this.beat -= float(layout.envelope.segments[this.seg_index].duration)
            if key == sdl2.SDLK_RIGHT:
                if this.seg_index and this.seg_index < len(layout.envelope.segments):
                    this.beat += float(layout.envelope.segments[this.seg_index].duration)
                    this.seg_index += 1

        @gui.drawing
        def _draw_(ui, comp):
            ctx = ui.ctx
            if ui.focus == comp.key:
                x = monotonic_interpolation(this.beat, beats, offsets, True)
                ctx.move_to(x,layout.y)
                ctx.line_to(x,layout.y+layout.height)
                ctx.stroke()

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
                if True:
                    base, dots, triplet = this.base_note, this.dots, this.tri
                    if triplet:
                        dots = 0
                    ctx.move_to(x + 15, layout.y - 10)
                    if base > 2:
                        text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                    else:
                        text = tab[base] + '.'*dots
                    ctx.show_text(text)
                    ctx.set_font_size(12)
                    ctx.move_to(x + 15, layout.y + 2)
                    ctx.show_text('3'*int(triplet))
                    if layout.envelope.kind == 'tempo':
                        ctx.set_font_size(12)
                        ctx.move_to(x + 35, layout.y - 15)
                        ctx.show_text(str(this.tapped))
        return
    first_voice_uid = None
    first_beat = 0.0
    first_index = 0
    for voice in track.voices:
        if voice.staff_uid == staff_uid:
            first_voice_uid = voice.uid
            for seg in voice.segments:
                first_beat += float(seg.duration)
                first_index += 1
            break

    this = gui.lazybundle(
        document = editor.document,
        voice_uid = first_voice_uid,
        seg_index = first_index,
        beat      = first_beat,
        stencil   = [],
        accidental = None,
        playing = [],
        time_start = None,
        base_note = Fraction(1, 4),
        dots = 0,
        tri = False,
    )
    if this.document != editor.document:
        this.document = editor.document
        this.voice_uid = first_voice_uid
        this.seg_index = first_index
        this.beat = first_beat
    def add_or_remove(position):
        for note in this.stencil:
            if note.pitch.position == position:
                this.stencil.remove(note)
                this._composition.set_dirty()
                return
        this.stencil.append(entities.Note(
            entities.Pitch(position, this.accidental),
            instrument_uid))
        this._composition.set_dirty()

    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        if button == 1:
            beatpoint = monotonic_interpolation(x / sf, offsets, beats)
            nearest = nearest_voice(trajectories, x / sf, y / sf, layout.staff.uid)
            this.voice_uid = nearest[0]

            for voice in track.voices:
                if this.voice_uid == voice.uid:
                    beat = 0.0
                    i = 0
                    for seg in voice.segments:
                        if beatpoint < beat + float(seg.duration) / 2:
                            break
                        beat += float(seg.duration)
                        i += 1
                    this.beat = beat
                    this.seg_index = i
        if button == 3:
            this.beat = 0.0
            this.voice_uid = None
            this.seg_index = 0

    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        if this.voice_uid is None:
            uid = editor.document.next_uid()
            track.voices.append(entities.Voice(uid, layout.staff.uid, None, []))
            this.voice_uid = uid
            this.seg_index = 0
        block = layout.by_beat(this.beat)
        i = (layout.staff.top*6 + layout.staff.bot*6) + block.clef + 1
        matrix = [
            sdl2.SDLK_v, sdl2.SDLK_b, sdl2.SDLK_n, sdl2.SDLK_m,
            sdl2.SDLK_g, sdl2.SDLK_h, sdl2.SDLK_j, sdl2.SDLK_k, sdl2.SDLK_l,
            sdl2.SDLK_y, sdl2.SDLK_u, sdl2.SDLK_i, sdl2.SDLK_o,
            sdl2.SDLK_7, sdl2.SDLK_8, sdl2.SDLK_9, sdl2.SDLK_0,
        ]
        if key in matrix:
            add_or_remove(i + matrix.index(key) - 8)
        ac_matrix = [ sdl2.SDLK_c, sdl2.SDLK_d, sdl2.SDLK_f, sdl2.SDLK_r, sdl2.SDLK_t ]
        if key in ac_matrix:
            accidental = ac_matrix.index(key) - 2
            this.accidental = None if this.accidental == accidental else accidental

        if repeat == 0 and key == sdl2.SDLK_p:
            def midi_event(m, plugin):
                @plugin.event
                def _event_():
                    buf = plugin.inputs['In']
                    plugin.push_midi_event(buf, [0x91, m, 0xFF])
            block = layout.by_beat(this.beat)
            key = resolution.canon_key(block.canonical_key)
            this.playing = []
            for note in list(this.stencil):
                if note.instrument_uid is None:
                    continue
                plugin = editor.transport.plugins[note.instrument_uid]
                m = resolution.resolve_pitch(note.pitch, key)
                midi_event(m, plugin)
                this.playing.append((m, plugin))

        if repeat == 0 and key == sdl2.SDLK_q:
            this.time_start = editor.time

        if key == sdl2.SDLK_a:
            this.base_note /= 2

        if key == sdl2.SDLK_w:
            this.base_note *= 2

        if key == sdl2.SDLK_z and this.dots > 0:
            this.dots -= 1

        if key == sdl2.SDLK_x:
            this.dots += 1

        if key == sdl2.SDLK_e:
            this.tri = not this.tri

        if key == sdl2.SDLK_z:
            this.stencil = []

        if key == sdl2.SDLK_BACKSPACE:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index > 0:
                    seg = voice.segments[this.seg_index-1]
                    voice.segments[this.seg_index-1:this.seg_index] = []
                    this.seg_index -= 1
                    this.beat -= float(seg.duration)
            this._composition.set_dirty()

        if key == sdl2.SDLK_SPACE:
            bpm = get_tempo_envelope(editor.document)
            editor.transport.play(bpm, editor.document.track.voices,
                dict((s.uid, s) for s in editor.document.track.graphs))

        seg = entities.VoiceSegment(
            notes = list(this.stencil),
            duration = resolution.build_note_duration(this.base_note, this.dots, this.tri) * block.beat_unit,
        )
        if key == sdl2.SDLK_1:
            for voice in track.voices:
                if this.voice_uid == voice.uid:
                    voice.segments[this.seg_index:this.seg_index] = [seg]
                    this.seg_index += 1
                    this.beat += float(seg.duration)
            this._composition.set_dirty()
        if key == sdl2.SDLK_2:
            for voice in track.voices:
                if this.voice_uid == voice.uid:
                    voice.segments[this.seg_index:this.seg_index+1] = [seg]
                    this.seg_index += 1
                    this.beat += float(seg.duration)
            this._composition.set_dirty()
        if key == sdl2.SDLK_3:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index < len(voice.segments):
                    seg.duration = voice.segments[this.seg_index].duration
                    voice.segments[this.seg_index:this.seg_index+1] = [seg]
                    this.seg_index += 1
                    this.beat += float(seg.duration)
            this._composition.set_dirty()
        if key == sdl2.SDLK_4:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index < len(voice.segments):
                    seg.notes = voice.segments[this.seg_index].notes
                    voice.segments[this.seg_index:this.seg_index+1] = [seg]
                    this.seg_index += 1
                    this.beat += float(seg.duration)
            this._composition.set_dirty()
        if key == sdl2.SDLK_LEFT:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index > 0:
                    this.seg_index -= 1
                    this.beat -= float(voice.segments[this.seg_index].duration)
        if key == sdl2.SDLK_RIGHT:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index < len(voice.segments):
                    this.beat += float(voice.segments[this.seg_index].duration)
                    this.seg_index += 1
        for voice in track.voices:
            if voice.uid == this.voice_uid and len(voice.segments) == 0:
                track.voices.remove(voice)
                this.voice_uid = None
                break

    @gui.listen(gui.e_key_up)
    def _up_(key, modifier):
        if key == sdl2.SDLK_p:
            def midi_event(m, plugin):
                @plugin.event
                def _event_():
                    buf = plugin.inputs['In']
                    plugin.push_midi_event(buf, [0x81, m, 0xFF])
            for m, plugin in this.playing:
                midi_event(m, plugin)
        if key == sdl2.SDLK_q:
            this.time_start = None

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        if ui.focus == comp.key:
            if this.voice_uid is None:
                ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
            else:
                ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
            x = monotonic_interpolation(this.beat, beats, offsets, True)
            y0 = layout.graph_point(layout.staff.top*12 - 1)
            y1 = layout.graph_point(layout.staff.bot*12 + 3)
            ctx.move_to(x,y0 - 20)
            ctx.line_to(x,y1 + 20)
            ctx.stroke()

            for note in this.stencil:
                ctx.set_source_rgba(*icolors.get(note.instrument_uid, (0.25,0.25,0.25,1.0)))
                pitch = note.pitch
                y = layout.note_position(this.beat, pitch.position)
                ctx.arc(x, y, 5, 0, math.pi*2)
                ctx.fill()
                if pitch.accidental is not None:
                    ctx.set_font_size(25)
                    xt = ctx.text_extents(resolution.char_accidental[pitch.accidental])
                    ctx.move_to(x - 8 - xt.width, y + 5)
                    ctx.show_text(resolution.char_accidental[pitch.accidental])

            ctx.set_font_size(10)
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
            ctx.move_to(x + 10,y0 - 10)
            if this.accidental is not None:
                ctx.show_text(resolution.char_accidental[this.accidental])

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
            block = layout.by_beat(this.beat)
            #cat = resolution.categorize_note_duration(this.duration / block.beat_unit)
            #if cat is not None:
            if True:
                base, dots, triplet = this.base_note, this.dots, this.tri
                if triplet:
                    dots = 0
                ctx.move_to(x + 15, y0 - 10)
                if base > 2:
                    text = (tab[Fraction(1,base.denominator)] + '.'*dots) * base.numerator
                else:
                    text = tab[base] + '.'*dots
                ctx.show_text(text)
                ctx.set_font_size(12)
                ctx.move_to(x + 15, y0 + 2)
                ctx.show_text('3'*int(triplet))
                ctx.set_font_size(25)

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

def staff_block(ctx, layout, x, block, smear):
    staff = layout.staff
    x0 = x
    if block.clef is not None:
        # Our version of a clef
        # Select most centered C, F, G in the staff
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        ctx.set_font_size(20)
        i = (staff.top*6 + staff.bot*6) + block.clef + 1
        j = i - i % 7
        p = min((j + x for x in [-7, -4, -3, 0, 3, 4] if (j + x - block.clef) % 2 == 1),
                key = lambda p: abs(p - i))
        y = layout.note_position(block.beat, p)
        t = resolution.pitch_name(entities.Pitch(p))
        ctx.move_to(x + 5 + 7, y+7)
        ctx.show_text(t)
        ctx.arc(x + 5, y, 5, 0, 2*math.pi)
        ctx.fill()

        #ctx.arc(x + 15, layout.note_position(block.beat, i), 5, 0, 2*math.pi)
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
                    position = i*12 + smear.clef + 11
                    c_pos = position - position % 7
                    if c_pos + 4 >= position + 2:
                        j = c_pos + sharp - 7
                    else:
                        j = c_pos + sharp - 7 * (sharp > 4)
                    ctx.move_to(x, layout.note_position(block.beat, j)+4)
                    ctx.show_text(resolution.char_accidental[1])
                x += 7
        else:
            for flat in reversed(resolution.sharps[canon_key:]):
                for i in range(staff.bot, staff.top):
                    position = i*12 + smear.clef + 11
                    j = (position - position % 7) + flat - 7 * (flat > 2)
                    # It is questionable to move them around like this,
                    # It seems that more likely there are several fixed patterns
                    # and one is used when it fits the best.
                    if j > position:
                        j -= 7
                    if j <= position - 10:
                        j += 7
                    ctx.move_to(x, layout.note_position(block.beat, j)+4)
                    ctx.show_text(resolution.char_accidental[-1])
                x += 7
        if block.beats_in_measure is not None or block.beat_unit is not None:
            ctx.set_source_rgba(0, 0, 0, 1)
            ctx.set_font_size(25)
            for i in range(staff.bot, staff.top):
                position = i*12 + 7
                ctx.move_to(x + 10, layout.graph_point(position)-2)
                ctx.show_text(str(smear.beats_in_measure))
                ctx.move_to(x + 10, layout.graph_point(position)+18)
                ctx.show_text(str(smear.beat_unit))
            x += 30
        return x - x0

class Editor:
    def __init__(self):
        self.document = entities.load_document('document.mide.zip')
        self.history = commands.History(self.document)
        self.history.do(commands.DemoCommand())
        self.pluginhost = lv2.PluginHost()
        self.transport = audio.Transport(
            self.document.init_plugins(self.pluginhost),
            self.document.mutes)
        self.audio_output = audio.DeviceOutput(self.transport)
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
                                self.audio_output.close()
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
        self.pluginhost.close()
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

if __name__=='__main__':
    Editor().ui()
