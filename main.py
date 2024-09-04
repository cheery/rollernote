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

e_document_change = object()
e_graph_button_down = object()
e_graph_button_up = object()
e_graph_motion = object()

@gui.composable
def vu_meter(vol, width=20, height=90):
    comp = gui.current_composition.get()
    gui.layout(gui.DynamicLayout(width, height))

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
        bb.trace(ctx)
        ctx.stroke()
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
        tool = super_tool,
        looping = False,
        instrument_uid = None,
        beatballs = [],
        dialogs = [],
    )

    @gui.sub
    def upper():
        gui.layout(gui.PaddedLayout(gui.RowLayout(flexible_width=True), 5, 5, 5, 5))
        vu_meter(editor.transport.volume_meter, height=32+48+5)
        gui.hspacing(5)
        @gui.column(flexible_height = True)
        def toolbars():
            @gui.row(height=32)
            def _row_():
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
                    document = editor.document
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
            gui.vspacing(5)
            @gui.row(height=48)
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
                    document = editor.document
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
                    this.tool = super_tool
                gui.hspacing(5)
                inputbutton = components.button2("input", font_size=32, flexible_height=True)
                @inputbutton.listen(gui.e_button_down)
                def _inputbutton_down_(x, y, button):
                    this.tool = input_tool
        gui.hspacing(5)
        @gui.sub
        def instrument_scroller():
            comp = gui.current_composition.get()
            gui.layout(gui.PaddedLayout(gui.DynamicLayout(width=200, height=32 + 48 + 5), 0, 10, 0, 0))
            that = gui.lazybundle(
                scroll_x = 0,
                scroll_y = 0,
                scale_x = 1,
                scale_y = 1,
                scrolling = False,
                scroll_y_was = 0,
                x = 0,
                y = 0)
            @gui.pre_drawing
            def _draw_(ui, comp):
                ui.ctx.set_source_rgba(0,0,0,1)
                comp.shape.trace(ui.ctx)
                ui.ctx.stroke()
                x = comp.shape.x + comp.shape.width - 7.5
                y = comp.shape.y + 2.5
                h = comp.shape.height - 5
                for child in comp.children:
                    height = child.layout.calc_height
                    inner_height = child.layout.inner.calc_height
                    ratio = height / inner_height if inner_height > 0 else 1.0
                    if ratio > 1.0:
                        ratio = 1.0
                    scroll_y = child.layout.scroll_y
                    max_scroll_y = child.layout.max_scroll()[1]
                    sratio = scroll_y / max_scroll_y if max_scroll_y > 0 else 0.0
                    d = h - h * ratio
                    ui.ctx.rectangle(x, y + d * sratio, 5, h * ratio)
                    if that.scrolling:
                        ui.ctx.stroke()
                    else:
                        ui.ctx.fill()
            @gui.listen(gui.e_button_down)
            def _down_(x, y, button):
                that.scrolling = True
                that.x = x
                that.y = y
                that.scroll_y_was = that.scroll_y
            @gui.listen(gui.e_button_up)
            def _up_(x, y, button):
                that.scrolling = False
            @gui.listen(gui.e_motion)
            @gui.listen(gui.e_dragging)
            def _motion_(x, y):
                if that.scrolling:
                    h = comp.shape.height - 5
                    for child in comp.children:
                        height = child.layout.calc_height
                        inner_height = child.layout.inner.calc_height
                        ratio = height / inner_height if inner_height > 0 else 1.0
                        scroll_y = child.layout.scroll_y
                        max_scroll_y = child.layout.max_scroll()[1]
                        sratio = scroll_y / max_scroll_y if max_scroll_y > 0 else 0.0
                        d = h - h * ratio
                        if d * max_scroll_y > 0:
                            that.scroll_y = (y - that.y) / d * max_scroll_y + that.scroll_y_was
                            that.scroll_y = child.layout.clamp_scroll(0, that.scroll_y)[1]

            @gui.sub
            def instrument_panel():
                comp = gui.current_composition.get()
                comp.clipping = True
                gui.layout(gui.ScrollableLayout(gui.ColumnLayout(), that, flexible_width=True, flexible_height=True))

                @gui.pre_drawing
                def _draw_(ui, comp):
                    ui.ctx.set_source_rgba(0,0,0,1)
                    comp.shape.trace(ui.ctx)
                    ui.ctx.stroke()

                @gui.composable
                def instrument_row(i, instrument):
                    plugin = editor.transport.plugins[instrument.uid]
                    gui.layout(gui.RowLayout(height=20, flexible_width=True))
                    components.colorbox(resolution.golden_ratio_color_varying(i), 10, flexible_height=True)
                    mute = editor.document.mutes.get(instrument.uid, 0)
                    stat = " ____"
                    if mute > 0:
                        stat = " mute"
                    if mute < 0:
                        stat = " solo"
                    label = f"{instrument.uid}: {plugin.name}"
                    comp = gui.current_composition.get()
                    openplugin = components.button2(label + stat, font_size=10, flexible_height=True)
                    @openplugin.listen(gui.e_button_down)
                    def _openplugin_down_(x, y, button):
                        if button == 1 and plugin.widget is None:
                            editor.widget(label, 120, 70, lv2.UIPayload, plugin)
                        elif button == 3:
                            @components.open_context_menu(comp, x, y)
                            def _context_menu_():
                                comp = gui.current_composition.get()
                                comp.layout.max_width = 150
                                dis = editor.document.mutes.get(instrument.uid,0) == +1
                                mut = components.button2("mute" + " (on)"*dis, flexible_width=True)
                                @mut.listen(gui.e_button_down)
                                def _mute_(x, y, button):
                                    mute = editor.document.mutes.get(instrument.uid, 0)
                                    if mute == +1:
                                        editor.document.mutes.pop(instrument.uid, None)
                                    else:
                                        editor.document.mutes[instrument.uid] = +1

                                dis = editor.document.mutes.get(instrument.uid,0) == -1
                                sol = components.button2("solo" + " (on)"*dis, flexible_width=True)
                                @sol.listen(gui.e_button_down)
                                def _solo_(x, y, button):
                                    mute = editor.document.mutes.get(instrument.uid, 0)
                                    if mute == -1:
                                        editor.document.mutes.pop(instrument.uid, None)
                                    else:
                                        editor.document.mutes[instrument.uid] = -1
                                clo = components.button2("clone", flexible_width=True)
                                @clo.listen(gui.e_button_down)
                                def _clone_(x, y, button):
                                    uid = editor.document.next_uid()
                                    i = f"instrument.{uid}"
                                    patch, data = editor.transport.plugins[instrument.uid].store(i)
                                    new_instrument = entities.Instrument(instrument.plugin, patch, data, uid)
                                    editor.document.instruments.append(new_instrument)
                                    sdl2.SDL_PauseAudio(1)
                                    editor.transport.plugins[new_instrument.uid] = plugin = editor.pluginhost.plugin(new_instrument.plugin)
                                    if len(new_instrument.patch) > 0:
                                        plugin.restore(new_instrument.patch, new_instrument.data)
                                    sdl2.SDL_PauseAudio(0)
                                era = components.button2("erase", flexible_width=True)
                                @era.listen(gui.e_button_down)
                                def _erase_(x, y, button):
                                    sdl2.SDL_PauseAudio(1)
                                    plugin = editor.transport.plugins[instrument.uid]
                                    plugin.close()
                                    editor.document.instruments.remove(instrument)
                                    for voice in editor.document.track.voices:
                                        for seg in voice.segments:
                                            for note in seg.notes:
                                                if note.instrument_uid == instrument.uid:
                                                    note.instrument_uid = None
                                    sdl2.SDL_PauseAudio(0)
                                    gui.inform(components.e_dialog_leave, comp)


                    selected = instrument.uid == this.instrument_uid
                    select = components.button2("X" if selected else "", font_size=10, disabled=selected, min_width=32, flexible_height=True)
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
                    if i > 0:
                        gui.vspacing(5)
                    instrument_row(i, instrument)

        gui.hspacing(5)
        @gui.column(width=200)
        def available_instruments():
            @gui.composable
            def available_instrument(uri, name):
                gui.layout(gui.RowLayout(height = 20, flexible_width = True))
                label = f"+ {name}"
                new_instrument = components.button2(label, font_size=10, flexible_height=True)
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
                if i > 0:
                    gui.vspacing(5)
                available_instrument(uri, name)

    @gui.sub
    def beatball_display():
        gui.layout(gui.DynamicLayout(flexible_width=True, height=50))
        @gui.listen(gui.e_update)
        def _update_():
            main_panel = next(main_scroller.children)
            beatline = main_panel.layout.inner
            beatballs = []
            for voice in list(editor.transport.live_voices):
                if voice.next_vseg > voice.last_vseg:
                    t = (editor.time - voice.last_vseg) / (voice.next_vseg - voice.last_vseg)
                else:
                    t = 0
                x0 = resolution.sequence_interpolation(voice.last_beat, beatline.beats, beatline.offsets, True)
                x1 = resolution.sequence_interpolation(voice.beat, beatline.beats, beatline.offsets, True)
                beat = voice.last_beat*(1-t) + voice.beat*t
                x = x0*(1-t) + x1*t
                beatballs.append((beat, x))
            this.beatballs = beatballs
        @gui.drawing
        def _draw_(ui, comp):
            main_panel = next(main_scroller.children)
            ui.ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
            for beat, x in this.beatballs:
                ui.ctx.arc(x*main_panel.layout.scale_x, comp.shape.y + 45 - 25 * abs(math.sin(beat * math.pi)), 5, 0, 2*math.pi)
                ui.ctx.stroke()

    @gui.sub
    def main_scroller():
        comp = gui.current_composition.get()
        gui.layout(gui.PaddedLayout(gui.DynamicLayout(flexible_width=True, flexible_height=True), 0, 10, 10, 0))
        that = gui.lazybundle(
            scroll_x = 0,
            scroll_y = 0,
            scale_x = 1.5,
            scale_y = 1.5,
            scrolling = False,
            scaling = False,
            scroll_x_was = 0,
            scroll_y_was = 0,
            scale_x_was = 1,
            scale_y_was = 1,
            x = 0,
            y = 0)
        @gui.pre_drawing
        def _draw_(ui, comp):
            ui.ctx.set_source_rgba(0,0,0,1)
            comp.shape.trace(ui.ctx)
            ui.ctx.stroke()
            x = comp.shape.x + comp.shape.width - 7.5
            y = comp.shape.y + 2.5
            h = comp.shape.height - 5 - 10
            for child in comp.children:
                height = child.layout.calc_height
                inner_height = child.layout.inner.calc_height * child.layout.scale_y
                ratio = height / inner_height if inner_height > 0 else 1.0
                if ratio > 1.0:
                    ratio = 1.0
                scroll_y = child.layout.scroll_y
                max_scroll_y = child.layout.max_scroll()[1]
                sratio = scroll_y / max_scroll_y if max_scroll_y > 0 else 0.0
                d = h - h * ratio
                ui.ctx.rectangle(x, y + d * sratio, 5, h * ratio)
                if that.scrolling:
                    ui.ctx.stroke()
                else:
                    ui.ctx.fill()
            x = comp.shape.x + 2.5
            y = comp.shape.y + comp.shape.height - 7.5
            w = comp.shape.width - 5 - 10
            for child in comp.children:
                width = child.layout.calc_width
                inner_width = child.layout.inner.calc_width * child.layout.scale_x
                ratio = width / inner_width if inner_width > 0 else 1.0
                if ratio > 1.0:
                    ratio = 1.0
                scroll_x = child.layout.scroll_x
                max_scroll_x = child.layout.max_scroll()[0]
                sratio = scroll_x / max_scroll_x if max_scroll_x > 0 else 0.0
                d = w - w * ratio
                ui.ctx.rectangle(x + d * sratio, y, w * ratio, 5)
                if that.scrolling:
                    ui.ctx.stroke()
                else:
                    ui.ctx.fill()
        @gui.listen(gui.e_button_down)
        def _down_(x, y, button):
            if button == 1:
                that.scrolling = True
            if button == 2:
                that.scale_x = 1
                that.scale_y = 1
            if button == 3:
                that.scaling = True
            that.x = x
            that.y = y
            that.scroll_x_was = that.scroll_x
            that.scroll_y_was = that.scroll_y
            that.scale_x_was = that.scale_x
            that.scale_y_was = that.scale_y
        @gui.listen(gui.e_button_up)
        def _up_(x, y, button):
            that.scrolling = False
            that.scaling = False
        @gui.listen(gui.e_motion)
        @gui.listen(gui.e_dragging)
        def _motion_(x, y):
            if that.scaling:
                delta = y - that.y
                that.scale_x = that.scale_x_was + delta / 100
                that.scale_y = that.scale_y_was + delta / 100
            if that.scrolling:
                h = comp.shape.height - 5 - 10
                for child in comp.children:
                    height = child.layout.calc_height
                    inner_height = child.layout.inner.calc_height * child.layout.scale_y
                    ratio = height / inner_height if inner_height > 0 else 1.0
                    scroll_y = child.layout.scroll_y
                    max_scroll_y = child.layout.max_scroll()[1]
                    sratio = scroll_y / max_scroll_y if max_scroll_y > 0 else 0.0
                    d = h - h * ratio
                    if d * max_scroll_y > 0:
                        that.scroll_y = (y - that.y) / d * max_scroll_y + that.scroll_y_was
                        that.scroll_y = child.layout.clamp_scroll(0, that.scroll_y)[1]
                w = comp.shape.width - 5 - 10
                for child in comp.children:
                    width = child.layout.calc_width
                    inner_width = child.layout.inner.calc_width * child.layout.scale_x
                    ratio = width / inner_width if inner_width > 0 else 1.0
                    scroll_x = child.layout.scroll_x
                    max_scroll_x = child.layout.max_scroll()[0]
                    sratio = scroll_x / max_scroll_x if max_scroll_x > 0 else 0.0
                    d = w - w * ratio
                    if d * max_scroll_x > 0:
                        that.scroll_x = (x - that.x) / d * max_scroll_x + that.scroll_x_was
                        that.scroll_x = child.layout.clamp_scroll(that.scroll_x, 0)[0]

        document = editor.document
        instrument_colors = {}
        for i, instrument in enumerate(document.instruments):
            instrument_colors[instrument.uid] = resolution.golden_ratio_color_varying(i)

        @gui.sub
        def main_panel():
            comp = gui.current_composition.get()
            comp.clipping = True
            gui.layout(gui.ScrollableLayout(BeatlineLayout(instrument_colors, document.track), that, flexible_width=True, flexible_height=True))

            @gui.pre_drawing
            def _draw_(ui, comp):
                ui.ctx.set_source_rgba(0,0,0,1)
                comp.shape.trace(ui.ctx)
                ui.ctx.stroke()

            for i, graph in enumerate(document.track.graphs):
                if i > 0:
                    gui.vspacing(5)
                if isinstance(graph, entities.Staff):
                    staff_display(editor, document, document.track, graph, this.tool, this.instrument_uid)
                elif isinstance(graph, entities.ChordProgression):
                    chord_progression_display(editor, document, document.track, graph, this.tool, this.instrument_uid)
                elif isinstance(graph, entities.Envelope):
                    envelope_display(editor, document, document.track, graph, this.tool, this.instrument_uid)
                else:
                    assert False

            beatline_events_display(document)

            if 'main' in this.tool:
                this.tool['main'](editor, document, this.instrument_uid)

            @gui.listen(gui.e_key_down)
            def _key_down_(key, repeat, modifier):
                if key == sdl2.SDLK_SPACE:
                    bpm = get_tempo_envelope(editor.document)
                    editor.transport.play(bpm, editor.document.track.voices,
                        dict((s.uid, s) for s in editor.document.track.graphs))

    gui.vspacing(5)
    @gui.row(height=32, flexible_width=True)
    def add_buttons():
        gui.hspacing(5)
        add_staff = components.button2("add staff", flexible_height=True)
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
        gui.hspacing(5)
        add_cp = components.button2("add chord prog.", flexible_height=True)
        @add_cp.listen(gui.e_button_down)
        def _add_cp_(x,y,button):
            editor.document.track.graphs.append(
                entities.ChordProgression(editor.document.next_uid(), []))
        gui.hspacing(5)
        add_e = components.button2("add envelope", flexible_height=True)
        @add_e.listen(gui.e_button_down)
        def _add_e_(x,y,button):
            editor.document.track.graphs.append(
                entities.Envelope(editor.document.next_uid(), "", []))

    gui.vspacing(5)
    components.label2(this.status)
    gui.vspacing(5)

    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        if repeat == 0:
            pass
            #@editor.plugin.event
            #def _event_():
            #    pass # TODO: fix
                #buf = editor.plugin.inputs['In']
                #editor.plugin.push_midi_event(buf, [0x91, key % 128, 127])

    @gui.listen(gui.e_key_up)
    def _up_(key, modifier):
        pass
        #@editor.plugin.event
        #def _event_():
        #    pass # TODO: fix
            #buf = editor.plugin.inputs['In']
            #editor.plugin.push_midi_event(buf, [0x81, key % 128, 127])

    for dialog, args, kwargs in this.dialogs:
        dialog(*args, **kwargs)

    comp = gui.current_composition.get()
    @gui.listen(components.e_dialog_open)
    def _dialog_open_(dialog, *args, **kwargs):
        this.dialogs.append((dialog, args, kwargs))
        comp.set_dirty()

    @gui.listen(components.e_dialog_leave)
    def _dialog_leave_():
        if len(this.dialogs) > 0:
            this.dialogs.pop()
            comp.set_dirty()

E_ENVELOPE_SEGMENT          = 4
E_CHORD_PROGRESSION_SEGMENT = 3
E_SEGMENT                   = 2
E_BLOCK                     = 1
E_BARLINE                   = 0

class BeatlineLayout(gui.ColumnLayout):
    def __init__(self, instrument_colors, track):
        super().__init__(gui.align_low, flexible_width=True, flexible_height=True)
        self.instrument_colors = instrument_colors
        self.track = track

        # Spacing configuration for note heads
        p = 20 # width of 1/128th beat note
        q = 50 # width of 1/1 beat note
        a = math.log(p / q) / math.log(1 / 128)
        self.spacing_conf = q,a

    def get_spacing(self, duration):
        q,a = self.spacing_conf
        return q * duration ** a

    def insert_event(self, beat, kind, value):
        bisect.insort_left(self.events, (beat, kind, value), key=lambda k: (k[0], k[1]))

    def measure(self, children, available_width, available_height):
        children = list(children)
        graphics = [child for child in children if isinstance(child.layout, GraphLayout)]
        self.x0 = max((child.layout.left_margin for child in graphics), default=0)

        self.graphs = {}
        self.layouts = {}
        self.envs = []
        for child in graphics:
            if isinstance(child.layout, EnvelopeLayout) and child.layout.envelope.kind == 'dynamics':
                self.envs.append(child.layout.envelope.uid)
            self.layouts[child.layout.uid] = child.layout
            self.graphs[child.layout.uid] = child

        # Computing positioning data for empty segments
        # from their empty neighbours
        empty_segment_position = {}
        for voice in self.track.voices:
            layout = self.layouts[voice.staff_uid]

            last_y = None
            rest_positions = []
    
            beat = 0
            for seg in voice.segments:
                if len(seg.notes) == 0:
                    # Store empty segment for later processing
                    rest_positions.append((beat, seg))
                else:
                    note_position = resolution.mean(note.pitch.position for note in seg.notes)
                    current_y = layout.note_position(beat, note_position)
                    # Assign this position to previous empty segments
                    for _, rest_seg in rest_positions:
                        if rest_seg not in empty_segment_position:
                            empty_segment_position[rest_seg] = []
                        if last_y is not None:
                            empty_segment_position[rest_seg].append(last_y)
                        empty_segment_position[rest_seg].append(current_y)
    
                    # Clear list of rest positions
                    rest_positions = []
                    last_y = current_y
                beat += float(seg.duration)
            # If rest positions are left over, fill them using the last known note position
            for beat, rest_seg in rest_positions:
                if last_y is not None:
                    if rest_seg not in empty_segment_position:
                        empty_segment_position[rest_seg] = []
                    empty_segment_position[rest_seg].append(last_y)
                elif rest_seg not in empty_segment_position:
                    empty_segment_position[rest_seg] = [layout.top_line, layout.bot_line]
        self.empty_segment_position = dict((seg, resolution.mean(positions)) for seg, positions in empty_segment_position.items())

        # Events on the beatline
        self.events = []

        # Breaking segments into measures
        for voice in self.track.voices:
            graph = self.graphs[voice.staff_uid]
            layout = self.layouts[voice.staff_uid]
            beat = 0.0
            remain = layout.beats_in_this_measure(beat)
            for seg in voice.segments:
                duration = seg.duration
                while remain < duration:
                    if remain > 0:
                        self.insert_event(beat, E_SEGMENT, (remain, seg, graph, voice))
                        duration -= remain
                        beat += float(remain)
                    remain = layout.beats_in_this_measure(beat)
                if duration != 0: # seg.duration <= remain
                    self.insert_event(beat, E_SEGMENT, (duration, seg, graph, voice))
                    remain -= duration
                    beat += float(duration)

        for graph in graphics:
            graph.layout.insert_events(self, graph)

        x = self.x0 + 20
        # Layout data to draw ties
        self.seg_xs = {}
        # Offsets and corresponding beat for drawing segment boxes/lines.
        self.offsets = [x]
        self.beats = [0.0]
        beat = 0.0
        #TODO: push = [0, 0, 0, 0, 0]
        push0 = 0
        push1 = 0

        self.barlines = []
        self.blocks = []
        self.segments = []
        self.envelope_segments = []
        self.chord_progression_segments = []

        self.trajectories = {}
        for voice in self.track.voices:
            self.trajectories[voice.uid] = (voice.staff_uid, voice.dynamics_uid, [], [])

        self.last_beat = max((l.last_beat for l in self.layouts.values()), default=0.0)

        # "Efficient algorithms for music engraving,
        #  focusing on correctness"
        for time, which, value in self.events:
            if which == E_BLOCK and push0 > 0:
                x += push0
                push0 = 0
            if which in [E_SEGMENT, E_CHORD_PROGRESSION_SEGMENT, E_ENVELOPE_SEGMENT] and push0 + push1 > 0:
                x += push0 + push1
                push0 = push1 = 0
                self.offsets.append(x)
                self.beats.append(beat)
            if beat < time:
                # Since we may render polyrhythms, we need to do spacing by beat.
                x += self.get_spacing(time - beat)
                beat = time
                self.offsets.append(x)
                self.beats.append(beat)
            if which == E_BLOCK:
                graph, block, smear, unusual = value
                if unusual:
                    self.barlines.append((True, x, graph))
                    self.blocks.append((graph, x+10, block, smear))
                    pushk = 20 + block_width(block)
                else:
                    self.blocks.append((graph, x, block, smear))
                    pushk = 10 + block_width(block)
                push1 = max(push1, pushk)
            if which == E_BARLINE:
                graph = value
                self.barlines.append((False, x, graph))
                push0 = 10
            if which == E_ENVELOPE_SEGMENT:
                graph, seg = value
                self.envelope_segments.append((beat, seg, graph, x))
            if which == E_CHORD_PROGRESSION_SEGMENT:
                layout, seg = value
                self.chord_progression_segments.append((beat, seg, layout, x))
            if which == E_SEGMENT:
                duration, seg, graph, voice = value
                tie = len(self.seg_xs.get(seg, []))
                self.segments.append((beat, x, tie, duration, seg, graph))
                staff_uid, dynamics_uid, xs, ys = self.trajectories[voice.uid]
                if len(seg.notes) > 0:
                    p = resolution.mean(note.pitch.position for note in seg.notes)
                    y = graph.layout.note_position(beat, p)
                else:
                    y = self.empty_segment_position[seg]
                xs.append(x)
                ys.append(y)
                        
                resolution.insert_in_list(self.seg_xs, seg, (beat, x))
        if beat < self.last_beat:
            x += self.get_spacing(self.last_beat - beat)
            self.offsets.append(x)
            self.beats.append(self.last_beat)
        for staff_uid, dynamics_uid, xs, ys in self.trajectories.values():
            layout = self.layouts[staff_uid]
            if len(xs) == 0:
                xs.append(x0 + 20)
                ys.append((layout.top_line + layout.bot_line) / 2)

        self.width = x
        super().measure(children, max(x, available_width), available_height)

    def location_as_position(self, graph, x, y):
        beat = resolution.sequence_interpolation(x, self.offsets, self.beats)
        clef = entities.by_beat(graph.layout.smeared, beat).clef
        return beat, round((graph.shape.y + graph.layout.reference - y) / 5) + graph.layout.staff.bot*12 + clef

    def nearest_voice(self, graph, x, y):
        closest = None
        distance = None
        for voice_uid, (staff_uid, dynamics_uid, xs, ys) in self.trajectories.items():
            if graph.layout.uid == staff_uid:
                ix = resolution.sequence_interpolation(x, xs, xs)
                iy = resolution.sequence_interpolation(x, xs, ys)
                d = (y - iy)**2 + (x - ix)**2
                if distance is None or d < distance:
                    distance = d
                    closest = voice_uid, (ix, iy)
        return closest

    def get_segment(self, refbeat, voice_uid):
        voice = self.get_voice(voice_uid)
        beat = 0.0
        for seg in voice.segments:
            if 0 <= refbeat - beat < float(seg.duration):
                return beat, seg
            beat += float(seg.duration)
        return beat, None

    def get_segment2(self, refbeat, voice_uid):
        voice = self.get_voice(voice_uid)
        beat = 0.0
        for seg in voice.segments:
            if refbeat - beat < float(seg.duration) / 2:
                return beat, seg
            beat += float(seg.duration)
        return beat, None

    def get_voice(self, voice_uid):
        for voice in self.track.voices:
            if voice.uid == voice_uid:
                return voice

def beatline_events_display(document):
    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        beatline = comp.layout.inner
        for dashed, x, graph in beatline.barlines:
            if dashed:
                ctx.set_dash([4, 2])
            ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
            ctx.move_to(x, graph.shape.y + graph.layout.top_line)
            ctx.line_to(x, graph.shape.y + graph.layout.bot_line)
            ctx.stroke()
            if dashed:
                ctx.set_dash([])

        for graph, x, block, smear in beatline.blocks:
            staff_block(ctx, graph.layout, x+10, graph.shape.y, block, smear)

        for voice_uid, (staff_uid, dynamics_uid, xs, ys) in beatline.trajectories.items():
            ctx.set_dash([4, 2])
            bb = beatline.graphs[staff_uid].shape
            mute = document.mutes.get(voice_uid, 0)
            color = [(1,1,0), (1,0,0), (0, 0, 0)][mute+1]
            ctx.set_source_rgb(*color)
            for i, (x,y) in enumerate(zip(xs, ys)):
                if i == 0:
                    ctx.move_to(x, bb.y + y)
                else:
                    ctx.line_to(x, bb.y + y)
            ctx.stroke()

            ctx.set_dash([8, 2])
            if dynamics_uid is not None:
                color = resolution.golden_ratio_color_varying(beatline.envs.index(dynamics_uid))
                ctx.set_source_rgba(*color)
                for i, (x,y) in enumerate(zip(xs, ys)):
                    if i == 0:
                        ctx.move_to(x, bb.y + y - 3)
                    else:
                        ctx.line_to(x, bb.y + y - 3)
                ctx.stroke()
        ctx.set_dash([])

        for beat, seg, graph, x0 in beatline.envelope_segments:
            bb = graph.shape
            ctx.set_source_rgba(0,0,0,1)
            x1 = resolution.sequence_interpolation(beat + float(seg.duration), beatline.beats, beatline.offsets, False)
            x2 = resolution.sequence_interpolation(beat + float(seg.duration), beatline.beats, beatline.offsets, True)
            if x2 - x1 < 10:
                x1 = x2 - 10
            if seg.control > 0:
                ctx.move_to(x0, bb.y + bb.height/2)
                ctx.line_to(x1, bb.y)
                ctx.move_to(x0, bb.y + bb.height/2)
                ctx.line_to(x1, bb.y + bb.height)
                ctx.stroke()
            elif seg.control < 0:
                ctx.move_to(x1, bb.y + bb.height/2)
                ctx.line_to(x0, bb.y)
                ctx.move_to(x1, bb.y + bb.height/2)
                ctx.line_to(x0, bb.y + bb.height)
                ctx.stroke()
            elif seg.value is not None:
                ctx.set_font_size(20)
                ctx.move_to(x0, bb.y + bb.height - 5)
                if graph.layout.envelope.kind.endswith('dynamics'):
                    levs =  [ 0.0,  0.2,  0.3,  0.4,  0.6, 0.7,  0.9]
                    texts = ['__', 'pp',  'p', 'mp', 'mf', 'f', 'ff']
                    i = bisect.bisect_right(levs, seg.value)
                    ctx.show_text(texts[i-1])
                else:
                    ctx.show_text(str(seg.value))
            else:
                ctx.set_source_rgba(0.7,0.7,0.7,1)
                ctx.move_to(x0, bb.y)
                ctx.line_to(x0, bb.y + bb.height)
                ctx.stroke()

        for beat, seg, graph, x0 in beatline.chord_progression_segments:
            bb = graph.shape
            ctx.set_source_rgba(0,0,0,1)
            ctx.set_font_size(20)
            ctx.move_to(x0, bb.y + bb.height)
            ctx.show_text(str(seg.nth))
            if document.mutes.get(graph.layout.uid, 0) > 0:
                continue
            x1 = resolution.sequence_interpolation(beat + float(seg.duration), beatline.beats, beatline.offsets, False)
            for graph in beatline.graphs.values():
                bb = graph.shape
                if isinstance(graph.layout, StaffLayout):
                    layout = graph.layout
                    block = entities.by_beat(graph.layout.smeared, beat)
                    if block.mode in ['minor', 'major']:
                        ton = resolution.tonic(block.canonical_key, {'minor': 5, 'major': 0}[block.mode])
                        low = layout.margin_bot*12 + block.clef
                        high = layout.margin_top*12 + block.clef
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
                                y = layout.note_position(beat, pos)
                                ctx.move_to(x0, bb.y + y+2)
                                ctx.line_to(x1, bb.y + y+2)
                                ctx.line_to(x1, bb.y + y-2)
                                ctx.line_to(x0, bb.y + y-2)
                                ctx.fill()

        for beat, x, tie, duration, seg, graph in beatline.segments:
            bb = graph.shape
            layout = graph.layout
            ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
            block = entities.by_beat(layout.smeared, beat)
            beat_unit = block.beat_unit
            cat, n, k, flex = resolution.flexible_categorize(duration, beat_unit, (-7,1,3))
                #if len(seg.notes) == 0:
                #    t = beatline.empty_segment_position[seg]
                #else:
                #    pos = resolution.mean(note.pitch.position for note in seg.notes)
                #    t = layout.note_position(beat, pos)
                #d = resolution.quantize_fraction(duration / beat_unit)
                #cat = resolution.categorize_note_duration(d)
                #base, dots, triplet = cat
            if flex:
                for center in layout.center_lines():
                    ctx.move_to(x, bb.y + center)
                    ctx.show_text('*')

            if len(seg.notes) == 0:
                y = beatline.empty_segment_position[seg]
                ctx.set_font_size(50)
                ctx.move_to(x - 4, bb.y + y -2)
                c = {
                    1: chr(119098),
                    0: chr(119099),
                   -1: chr(119100),
                   -2: chr(119101),
                   -3: chr(119102),
                   -4: chr(119103),
                   -5: chr(119104),
                   -6: chr(119105),
                   -7: chr(119106),
                }[n]
                ctx.show_text(c)
                if cat == 'fragment':
                    ctx.set_font_size(10)
                    ctx.move_to(x - 4, bb.y + y + 5)
                    ctx.show_text(str(k))
                if cat == 'dotted':
                    for dot in range(k):
                        ctx.arc(x + 16 + dot*5, bb.y + y + 3, 2, 0, 2*math.pi)
                        ctx.fill()
                if cat == 'repeated':
                    ctx.move_to(x - 4, bb.y + y + 5)
                    ctx.show_text('*' + str(k))
            for note in seg.notes:
                ctx.set_source_rgba(0,0,0,1)
                pitch = note.pitch
                y = layout.note_position(beat, pitch.position)
                # TODO: render accidental only when it changes in measure.
                if pitch.accidental is not None:
                    ctx.set_font_size(25)
                    xt = ctx.text_extents(resolution.char_accidental[pitch.accidental])
                    ctx.move_to(x - 8 - xt.width, bb.y + y + 5)
                    ctx.show_text(resolution.char_accidental[pitch.accidental])
                # TODO: represent triplet with some smarter way
                ctx.move_to(x +5, bb.y + y)
                ctx.arc(x, bb.y + y, 5, 0, 2*math.pi)
                if n >= -1:
                    ctx.stroke()
                else:
                    ctx.fill()
                if cat == 'fragment':
                    ctx.set_font_size(10)
                    ctx.move_to(x + 5, bb.y + y + 5)
                    ctx.show_text(str(k))
                if cat in ('dotted', 'repeated'):
                    if cat == 'dotted':
                        for dot in range(k):
                            ctx.arc(x + 8 + dot*5, bb.y + y + 3, 2, 0, 2*math.pi)
                            ctx.fill()
                    if cat == 'repeated':
                        ctx.move_to(x, bb.y + y + 5)
                        ctx.show_text('*'+str(k))
                if tie > 0:
                    past, px = beatline.seg_xs[seg][tie-1]
                    y0 = layout.note_position(past, pitch.position)
                    ctx.move_to(px+8, bb.y + y0 + 3)
                    ctx.curve_to(px+8, 8 + bb.y + y0 + 3,
                                  x-8, 8 + bb.y + y + 3,
                                  x-8, 0 + bb.y + y + 3)
                    ctx.stroke()
                ctx.set_source_rgba(*beatline.instrument_colors.get(note.instrument_uid, (0.25,0.25,0.25,1.0)))
                ctx.arc(x - 2, bb.y + y + 2, 3, 0, 2*math.pi)
                ctx.fill()
            ctx.set_source_rgba(0,0,0,1)
            if len(seg.notes) > 0:
                high = min(layout.note_position(beat, note.pitch.position) for note in seg.notes)
                low = max(layout.note_position(beat, note.pitch.position) for note in seg.notes)
                if high < low:
                    ctx.move_to(x + 5, bb.y + high)
                    ctx.line_to(x + 5, bb.y + low)
                    ctx.stroke()
                if n <= -1:
                    ctx.move_to(x + 5, bb.y + high)
                    ctx.line_to(x + 5, bb.y + high - 30)
                    ctx.stroke()
                for d in range(5):
                    if n <= -3-d:
                        ctx.move_to(x + 5, bb.y + high - 30 + d * 4)
                        ctx.line_to(x + 5 + 5, bb.y + high - 30 + d * 4 + 8)
                        ctx.stroke()

class GraphLayout(gui.DynamicLayout):
    pass

e_margin_press = object()

@gui.composable
def staff_display(editor, document, track, staff, tool, instrument_uid):
    gui.layout(StaffLayout(track, staff))
    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        # Staff lines
        # These are rendered without refering
        # to anything else but staff.top and staff.bot and margins
        bb = comp.shape
        for i in range(comp.layout.start, comp.layout.stop, 2):
            if i % 12 != 2:
                k = i * 5
                ctx.move_to(0,        bb.y + k)
                ctx.line_to(bb.width, bb.y + k)
                ctx.stroke()

        initial = entities.by_beat(comp.layout.smeared, 0.0)
        canon_key = initial.canonical_key
        key = resolution.canon_key(canon_key)

        # Major/Minor letters above the 'clef'
        major = entities.Pitch(resolution.tonic(canon_key))
        minor = entities.Pitch(resolution.tonic(canon_key, 5))
        major_text = resolution.pitch_name(major, key, show_octave=False)
        minor_text = resolution.pitch_name(minor, key, show_octave=False)
        ctx.set_font_size(10)
        ctx.move_to(35, bb.y + 9)
        ctx.show_text(f"{major_text} {minor_text}m") # Initial pitch markings ctx.set_font_size(10) clef = initial.clef
        for i in range(0, comp.layout.span, 2):
            position = i + comp.layout.margin_bot*12 + initial.clef
            t = resolution.pitch_name(entities.Pitch(position), key)
            ctx.move_to(10, bb.y + comp.layout.note_position(0.0, position) + 4)
            ctx.show_text(t)

        x0 = comp.parent.layout.inner.x0
        staff_block(ctx, comp.layout, x0 - comp.layout.left_margin + 35, bb.y, initial, initial)

        # bar
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        ctx.move_to(x0, bb.y + comp.layout.top_line)
        ctx.line_to(x0, bb.y + comp.layout.bot_line)
        ctx.stroke()

        mute = document.mutes.get(staff.uid, 0)
        ctx.set_font_size(20)
        ctx.move_to(x0, bb.y + 20)
        ctx.show_text(['solo', '', 'mute'][mute+1])
        ctx.stroke()

    staff_tool = tool.get('staff')
    if staff_tool:
        staff_tool(editor, instrument_uid)

    comp = gui.current_composition.get()
    @gui.listen(e_document_change)
    def _document_change_():
        comp.set_dirty()

    @gui.listen(e_margin_press) # TODO: remove when ready
    @gui.listen(gui.e_button_down)
    def _press_(x, y, button):
        beatline = comp.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            if button == 1:
                gui.inform(components.e_dialog_open, comp, staff_dialog, editor, comp.layout.staff)
            if button == 2:
                mute = editor.document.mutes.get(comp.layout.uid, 0)
                if mute == -1:
                    editor.document.mutes.pop(comp.layout.uid, None)
                else:
                    editor.document.mutes[comp.layout.uid] = -1
            if button == 3:
                mute = editor.document.mutes.get(comp.layout.uid, 0)
                if mute == 1:
                    editor.document.mutes.pop(comp.layout.uid, None)
                else:
                    editor.document.mutes[comp.layout.uid] = 1
            comp.set_dirty()
        else:
            gui.inform(e_graph_button_down, comp, x, y, button, comp)

    @gui.listen(gui.e_button_up)
    def _button_up_(x, y, button):
        gui.inform(e_graph_button_up, comp, x, y, button, comp)

    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        gui.inform(e_graph_motion, comp, x, y, comp)

class StaffLayout(GraphLayout):
    def __init__(self, track, staff):
        self.uid = staff.uid
        self.track = track
        self.staff = staff
        self.smeared = smeared = entities.smear(staff.blocks)
        # beat extent and lowest/highest note
        self.last_beat = 0.0
        lowest = highest = 0
        for voice in track.voices:
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
        self.start = (self.margin_top - staff.top)*12+2
        self.stop = (self.margin_top - staff.bot)*12+2
        self.reference = (self.stop+1) * 5
        # Layout calculation begins
        self.left_margin = 35 + block_width(entities.by_beat(smeared, 0.0))
        super().__init__(flexible_width=True, height=self.span * 5)
        self.top_line = self.graph_point(staff.top*12 - 1)
        self.bot_line = self.graph_point(staff.bot*12 + 3)

    def graph_point(self, index):
        return self.reference - (index - self.staff.bot*12)*5

    def note_position(self, beat, position):
        clef = entities.by_beat(self.smeared, beat).clef
        return self.reference - (position - self.staff.bot*12 - clef)*5

    def center_lines(self):
        for i in range(self.staff.bot, self.staff.top):
            yield self.graph_point(i*12 + 7)

    # Breaking segments into measures
    def beats_in_this_measure(self, beat):
        this, future = entities.at_beat(self.smeared, beat)
        if future is None:
            return this.beats_in_measure #, False
        else:
            distance = future.beat - beat
            if distance < this.beats_in_measure:
                return distance #, True
            else:
                return this.beats_in_measure #, False

    def insert_events(self, beatline, graph):
        previous = self.smeared[0]
        for i, smear in enumerate(self.smeared[1:], 1):
            for stop in resolution.frange(previous.beat + previous.beats_in_measure, smear.beat, previous.beats_in_measure):
                beatline.insert_event(stop, E_BARLINE, graph)
            block = self.staff.blocks[i]
            unusual = (smear.beat - previous.beat) % previous.beats_in_measure != 0
            beatline.insert_event(block.beat, E_BLOCK, (graph, block, smear, unusual))
            previous = smear
        for stop in resolution.frange(previous.beat + previous.beats_in_measure, self.last_beat, previous.beats_in_measure, inclusive=True):
            beatline.insert_event(stop, E_BARLINE, graph)

@gui.composable
def chord_progression_display(editor, document, track, chord_progression, tool, instrument_uid):
    gui.layout(ChordProgressionLayout(track, chord_progression))
    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        ctx.set_dash([4,2])
        bb = comp.shape
        ctx.move_to(0,        bb.y + bb.height)
        ctx.line_to(bb.width, bb.y + bb.height)
        ctx.stroke()

    chord_progression_tool = tool.get('chord_progression')
    if chord_progression_tool:
        chord_progression_tool(editor, instrument_uid)

    comp = gui.current_composition.get()
    @gui.listen(e_document_change)
    def _document_change_():
        comp.set_dirty()

    @gui.listen(e_margin_press)
    @gui.listen(gui.e_button_down)
    def _press_(x, y, button):
        beatline = comp.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            if button == 3:
                mute = document.mutes.get(comp.layout.uid, 0)
                if mute == 1:
                     document.mutes.pop(comp.layout.uid, None)
                else:
                     document.mutes[comp.layout.uid] = 1
        else:
            gui.inform(e_graph_button_down, comp, x, y, button, comp)

    @gui.listen(gui.e_button_up)
    def _button_up_(x, y, button):
        gui.inform(e_graph_button_up, comp, x, y, button, comp)

    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        gui.inform(e_graph_motion, comp, x, y, comp)

class ChordProgressionLayout(GraphLayout):
    def __init__(self, track, chord_progression):
        self.uid = chord_progression.uid
        self.track = track
        self.chord_progression = chord_progression
        self.last_beat = sum(float(seg.duration) for seg in chord_progression.segments)
        self.left_margin = 10
        super().__init__(flexible_width=True, height=20)

    def insert_events(self, beatline, graph):
        beat = 0.0
        for seg in self.chord_progression.segments:
            beatline.insert_event(beat, E_CHORD_PROGRESSION_SEGMENT, (graph, seg))
            beat += float(seg.duration)

@gui.composable
def envelope_display(editor, document, track, envelope, tool, instrument_uid):
    gui.layout(EnvelopeLayout(track, envelope))
    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        ctx.set_dash([8,2])
        bb = comp.shape
        ctx.move_to(0,        bb.y + bb.height)
        ctx.line_to(bb.width, bb.y + bb.height)
        ctx.stroke()
        ctx.set_dash([])
        ctx.move_to(10, bb.y + bb.height)
        ctx.set_font_size(20)
        ctx.show_text(envelope.kind)
        if envelope.kind == 'dynamics':
            i = comp.parent.layout.inner.envs.index(envelope.uid)
            color = resolution.golden_ratio_color_varying(i)
            ctx.set_source_rgba(*color)
            ctx.rectangle(comp.parent.layout.inner.x0 - 10, bb.y + bb.height - 11, 10, 10)
            ctx.fill()

    envelope_tool = tool.get('envelope')
    if envelope_tool:
        envelope_tool(editor, instrument_uid)

    comp = gui.current_composition.get()
    @gui.listen(e_document_change)
    def _document_change_():
        comp.set_dirty()

    @gui.listen(e_margin_press)
    @gui.listen(gui.e_button_down)
    def _press_(x, y, button):
        beatline = comp.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            if button == 1:
                gui.inform(components.e_dialog_open, comp, envelope_dialog, editor, comp.layout.envelope)
        else:
            gui.inform(e_graph_button_down, comp, x, y, button, comp)

    @gui.listen(gui.e_button_up)
    def _button_up_(x, y, button):
        gui.inform(e_graph_button_up, comp, x, y, button, comp)

    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        gui.inform(e_graph_motion, comp, x, y, comp)

class EnvelopeLayout(GraphLayout):
    def __init__(self, track, envelope):
        self.uid = envelope.uid
        self.track = track
        self.envelope = envelope
        self.last_beat = sum(float(seg.duration) for seg in envelope.segments)
        self.left_margin = 10
        super().__init__(flexible_width=True, height=20)

    def insert_events(self, beatline, graph):
        beat = 0.0
        for seg in self.envelope.segments:
            beatline.insert_event(beat, E_ENVELOPE_SEGMENT, (graph, seg))
            beat += float(seg.duration)

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

def super_tool_main(editor, document, instrument_uid):
    comp = gui.current_composition.get()
    this = gui.lazybundle(
        voice_lock = False,
        ctrl = False,
        pressing = False,
        pressed_x = 0,
        pressed_y = 0,
        mouse_x = 0,
        mouse_y = 0,
        seg_selection = set(),
        note_selection = set(),
        nearest = None,
        graph_uid = None,
        beat = 0.0,
        position = None,
        playing = [],
    )

    @gui.listen(e_document_change)
    def _document_change_():
        comp.set_dirty()

    def retrieve_segments(selected, expanding, for_repr=False):
        beatline = comp.layout.inner
        x0 = min(this.pressed_x, this.mouse_x)
        x1 = max(this.pressed_x, this.mouse_x)
        voice = beatline.get_voice(this.nearest[0])
        beat = 0.0
        for i, seg in enumerate(voice.segments):
            x = resolution.sequence_interpolation(beat, beatline.beats, beatline.offsets, True)
            if (expanding and x0 <= x <= x1) or i in selected:
                if for_repr:
                    _, _, xs, ys = beatline.trajectories[voice.uid]
                    y = resolution.sequence_interpolation(x, xs, ys)
                    yield (beat, i, seg, x, y)
                else:
                    yield i
            beat += float(seg.duration)

    def retrieve_notes(selected, expanding, for_repr=False):
        beatline = comp.layout.inner
        graph = beatline.graphs[this.graph_uid]
        x0 = min(this.pressed_x, this.mouse_x)
        x1 = max(this.pressed_x, this.mouse_x)
        y0 = min(this.pressed_y, this.mouse_y)
        y1 = max(this.pressed_y, this.mouse_y)
        voice = beatline.get_voice(this.nearest[0])
        beat = 0.0
        for i, seg in enumerate(voice.segments):
            x = resolution.sequence_interpolation(beat, beatline.beats, beatline.offsets, True)
            for note in seg.notes:
                position = note.pitch.position
                y = graph.layout.note_position(beat, position)
                s = (i, position) in selected
                if s or (expanding and x0 <= x <= x1 and y0 <= y + graph.shape.y <= y1):
                    if for_repr:
                        yield (beat, i, seg, note, x, y)
                    else:
                        yield i, position
            beat += float(seg.duration)

    @gui.listen(gui.e_motion)
    @gui.listen(e_graph_motion)
    def _motion_(x, y, graph=None):
        beatline = comp.layout.inner
        x, y = comp.local_point(x, y)
        this.mouse_x = x
        this.mouse_y = y
        if graph is not None and isinstance(graph.layout, StaffLayout):
            if not this.voice_lock and not this.pressing and not this.seg_selection and not this.note_selection:
                this.nearest = beatline.nearest_voice(graph, x, y)
                this.graph_uid = graph.layout.uid
            if this.graph_uid == graph.layout.uid:
                beat_position = beatline.location_as_position(graph, x, y)
                if beat_position is not None:
                    this.beat, this.position = beat_position
                else:
                    this.beat, this.position = 0.0, None

    @gui.listen(e_graph_button_down)
    @gui.listen(gui.e_button_down)
    def _button_down_(gx, gy, button, graph=None):
        beatline = comp.layout.inner
        x, y = comp.local_point(gx, gy)
        this.pressed_x = x
        this.pressed_y = y
        if this.position is not None and this.nearest is not None:
            beat, seg = beatline.get_segment2(this.beat, this.nearest[0])
            if button == 1 and seg is not None:
                sx = resolution.sequence_interpolation(beat, beatline.beats, beatline.offsets, True)
                if abs(x - sx) <= 5:
                    if not any(note.pitch.position == this.position for note in seg.notes):
                        if not this.ctrl:
                            this.note_selection = set()
                            this.seg_selection = set()
                        seg.notes.append(entities.Note(
                            entities.Pitch(this.position),
                            instrument_uid))
                        graph = beatline.graphs[this.graph_uid]
                        graph.set_dirty()
                    else:
                        voice = beatline.get_voice(this.nearest[0])
                        i = voice.segments.index(seg)
                        if not (this.ctrl or (i, this.position) in this.note_selection):
                            this.note_selection = set()
                            this.seg_selection = set()
                        this.seg_selection.add(i)
                        this.note_selection.add((i, this.position))
                        this.position = None
                        @components.open_context_menu(comp, gx, gy)
                        def _context_menu_():
                            def transpose(c):
                                def _fn_(x, y, button):
                                    for i, seg in enumerate(voice.segments):
                                        for note in list(seg.notes):
                                            if (i,note.pitch.position) in this.note_selection:
                                                note.pitch = entities.Pitch(note.pitch.position+c, note.pitch.accidental)
                                    this.note_selection = set((i, p+c) for i, p in this.note_selection)
                                    gui.broadcast(e_document_change)
                                return _fn_
                            def set_accidental(k):
                                def _fn_(x, y, button):
                                    for i, seg in enumerate(voice.segments):
                                        for note in list(seg.notes):
                                            if (i,note.pitch.position) in this.note_selection:
                                                note.pitch = entities.Pitch(note.pitch.position, k)
                                    gui.broadcast(e_document_change)
                                return _fn_
                            menu = gui.current_composition.get()
                            menu.layout.max_width = 200
                            @gui.row(flexible_width=True, height=32)
                            def _row_():
                                for acc in [-2,-1,0,None,+1,+2]:
                                    if acc is None:
                                        a = components.button2(' ', flexible_width=True, flexible_height=True)
                                    else:
                                        a = components.button2(resolution.char_accidental[acc], flexible_width=True, flexible_height=True)
                                    a.listen(gui.e_button_down)(set_accidental(acc))
                            @gui.row(flexible_width=True)
                            def _row_():
                                tup = components.button2('up', flexible_width=True)
                                tup.listen(gui.e_button_down)(transpose(1))
                                _8va = components.button2('8va', flexible_width=True)
                                _8va.listen(gui.e_button_down)(transpose(7))
                            @gui.row(flexible_width=True)
                            def _row_():
                                tdo = components.button2('down', flexible_width=True)
                                tdo.listen(gui.e_button_down)(transpose(-1))
                                _8vb = components.button2('8vb', flexible_width=True)
                                _8vb.listen(gui.e_button_down)(transpose(-7))

                            ins = components.button2('instrument', flexible_width=True)
                            @ins.listen(gui.e_button_down)
                            def _ins_down_(x, y, button):
                                for i, seg in enumerate(voice.segments):
                                    for note in list(seg.notes):
                                        if (i,note.pitch.position) in this.note_selection:
                                            note.instrument_uid = instrument_uid
                                this.position = None
                                gui.inform(components.e_dialog_leave, comp)
                                gui.broadcast(e_document_change)
                            era = components.button2('erase', flexible_width=True)
                            @era.listen(gui.e_button_down)
                            def _era_down_(x, y, button):
                                for i, seg in enumerate(voice.segments):
                                    for note in list(seg.notes):
                                        if (i,note.pitch.position) in this.note_selection:
                                            seg.notes.remove(note)
                                this.position = None
                                gui.inform(components.e_dialog_leave, comp)
                                gui.broadcast(e_document_change)
                elif button == 1:
                    this.pressing = True
                    if not this.ctrl:
                        this.note_selection = set()
                        this.seg_selection = set()
            if button == 3:
                this.voice_lock = not this.voice_lock

    @gui.listen(e_graph_button_up)
    @gui.listen(gui.e_button_up)
    def _button_up_(x, y, button, graph=None):
        if button == 1 and this.pressing:
            this.pressing = False
            this.note_selection = set(retrieve_notes(this.note_selection, True))
            this.seg_selection = set(retrieve_segments(this.seg_selection, True))
    @gui.listen(gui.e_key_down)
    def _keydown_(key, repeat, modifier):
        beatline = comp.layout.inner
        if this.nearest is not None:
            if key == sdl2.SDLK_m:
                mute = editor.document.mutes.get(this.nearest[0], 0)
                if mute == 1:
                    editor.document.mutes.pop(this.nearest[0], None)
                else:
                    editor.document.mutes[this.nearest[0]] = 1
            if key == sdl2.SDLK_s:
                mute = editor.document.mutes.get(this.nearest[0], 0)
                if mute == -1:
                    editor.document.mutes.pop(this.nearest[0], None)
                else:
                    editor.document.mutes[this.nearest[0]] = -1
            if key == sdl2.SDLK_d:
                envs = beatline.envs
                voice = beatline.get_voice(this.nearest[0])
                if voice.dynamics_uid is None and len(envs) > 0:
                    voice.dynamics_uid = envs[0]
                elif voice.dynamics_uid is not None:
                    i = envs.index(voice.dynamics_uid) + 1
                    if i < len(envs):
                        voice.dynamics_uid = envs[i]
                    else:
                        voice.dynamics_uid = None
                comp.set_dirty()
        if repeat == 0 and key == sdl2.SDLK_p and this.position is not None:
            def midi_event(m, plugin):
                @plugin.event
                def _event_():
                    buf = plugin.inputs['In']
                    plugin.push_midi_event(buf, [0x91, m, 127])
            graph = beatline.graphs[this.graph_uid]
            block = entities.by_beat(graph.layout.smeared, this.beat)
            key = resolution.canon_key(block.canonical_key)
            this.playing = []
            if instrument_uid is not None:
                plugin = editor.transport.plugins[instrument_uid]
                m = resolution.resolve_pitch(entities.Pitch(this.position, None), key)
                midi_event(m, plugin)
                this.playing.append((m, plugin))
        if key == sdl2.SDLK_LCTRL or key == sdl2.SDLK_RCTRL:
            this.ctrl = True

    @gui.listen(gui.e_key_up)
    def _up_(key, modifier):
        if key == sdl2.SDLK_p:
            def midi_event(m, plugin):
                @plugin.event
                def _event_():
                    buf = plugin.inputs['In']
                    plugin.push_midi_event(buf, [0x81, m, 127])
            for m, plugin in this.playing:
                midi_event(m, plugin)
        if key == sdl2.SDLK_LCTRL or key == sdl2.SDLK_RCTRL:
            this.ctrl = False

    @gui.drawing
    def _draw_(ui, comp):
        beatline = comp.layout.inner
        graph = beatline.graphs.get(this.graph_uid)
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        if this.pressing:
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
            ctx.set_dash([4,4])
            x0 = min(this.pressed_x, this.mouse_x)
            x1 = max(this.pressed_x, this.mouse_x)
            y0 = min(this.pressed_y, this.mouse_y)
            y1 = max(this.pressed_y, this.mouse_y)
            ctx.rectangle(x0, y0, x1-x0, y1-y0)
            ctx.stroke()
            ctx.set_dash([])
        if this.nearest is not None:
            for beat, i, seg, note, x, y in retrieve_notes(this.note_selection, this.pressing, for_repr=True):
                ctx.set_source_rgba(*beatline.instrument_colors.get(note.instrument_uid, (0.75,0.75,0.75,1.0)))
                ctx.arc(x, graph.shape.y + y, 5, 0, 2*math.pi)
                ctx.stroke()
            for beat, i, seg, x, y in retrieve_segments(this.seg_selection, this.pressing, for_repr=True):
                ctx.set_source_rgba(0, 0, 1)
                ctx.rectangle(x - 7, graph.shape.y + y + 2, 2, 8)
                ctx.rectangle(x + 5, graph.shape.y + y + 2, 2, 8)
                ctx.rectangle(x - 7, graph.shape.y + y + 8, 12, 2)
                ctx.fill()
        if this.voice_lock:
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
        if this.nearest is not None:
            staff_uid, dynamics_uid, xs, ys = beatline.trajectories[this.nearest[0]]
            bb = graph.shape
            for i, (x,y) in enumerate(zip(xs, ys)):
                if i == 0:
                    ctx.move_to(x, bb.y + y)
                else:
                    ctx.line_to(x, bb.y + y)
            ctx.stroke()
        if not this.pressing and this.position is not None:
            ctx.set_source_rgba(*beatline.instrument_colors.get(instrument_uid, (0.25,0.25,0.25,1.0)))
            beat, _ = beatline.get_segment2(this.beat, this.nearest[0])
            x = resolution.sequence_interpolation(beat, beatline.beats, beatline.offsets, True)
            y = graph.layout.note_position(this.beat, this.position)
            if abs(x - this.mouse_x) < 5:
                ctx.arc(x, graph.shape.y + y, 5, 0, 2*math.pi)
                ctx.fill()

super_tool = {'main': super_tool_main}

def transport_tool_main(editor, document, instrument_uid):
    comp = gui.current_composition.get()
    this = gui.lazybundle(
        mouse_x = 0,
        mouse_y = 0,
        beat = 0,
        head = 0,
        tail = 0,
        dragging = False
    )
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        beatline = comp.layout.inner
        x, y = comp.local_point(x, y)
        this.mouse_x = x
        this.mouse_y = y
        this.beat = round(resolution.sequence_interpolation(x, beatline.offsets, beatline.beats))
        if this.dragging:
            this.head = this.beat
            editor.transport.play_start = min(this.tail, this.head)
            editor.transport.play_end   = max(this.tail, this.head)

    @gui.listen(gui.e_button_down)
    @gui.listen(e_graph_button_down)
    def _down_(x, y, button, graph=None):
        beatline = comp.layout.inner
        if button == 1:
            editor.transport.play_start = this.beat
            editor.transport.play_end   = this.beat
            this.head = this.beat
            this.tail = this.beat
            this.dragging = True
            comp.set_dirty()
        if button == 3:
            @components.open_context_menu(comp, x, y)
            def _context_menu_():
                clr = components.button2("clear selection")
                @clr.listen(gui.e_button_down)
                def _clr_down_(x, y, button):
                    editor.transport.play_start = None
                    editor.transport.play_end = None
                    comp.set_dirty()
                    gui.inform(components.e_dialog_leave, comp)

    @gui.listen(gui.e_button_up)
    @gui.listen(e_graph_button_up)
    def _up_(x, y, button, graph=None):
        this.dragging = False

    @gui.drawing
    def _draw_(ui, comp):
        beatline = comp.layout.inner
        height = beatline.calc_height
        ctx = ui.ctx
        x = resolution.sequence_interpolation(this.beat, beatline.beats, beatline.offsets, True)
        ctx.set_source_rgba(1,0,0,1)
        ctx.move_to(x, 0)
        ctx.line_to(x, height)
        ctx.stroke()

        if editor.transport.play_start is not None and editor.transport.play_end is not None:
            x = resolution.sequence_interpolation(this.head, beatline.beats, beatline.offsets, True)
            ctx.set_source_rgba(0,0,1,1)
            ctx.move_to(x, 0)
            ctx.line_to(x, height)
            ctx.stroke()

        if editor.transport.play_start is not None:
            ctx.set_source_rgba(0,0,0,0.7)
            x0 = resolution.sequence_interpolation(0.0, beatline.beats, beatline.offsets, True)
            x1 = resolution.sequence_interpolation(editor.transport.play_start, beatline.beats, beatline.offsets, True)
            ctx.rectangle(x0, 0, x1 - x0, height)
            ctx.fill()
        if editor.transport.play_end is not None:
            ctx.set_source_rgba(0,0,0,0.7)
            x2 = resolution.sequence_interpolation(editor.transport.play_end, beatline.beats, beatline.offsets, True)
            x3 = resolution.sequence_interpolation(beatline.last_beat, beatline.beats, beatline.offsets, True)
            ctx.rectangle(x2, 0, x3 - x2, height)
            ctx.fill()

transport_tool = {'main': transport_tool_main}

@gui.composable
def staff_split_tool(editor, instrument_uid):
    comp = gui.current_composition.get()
    gui.layout(gui.DynamicLayout())
    this = gui.lazybundle(
        voice_lock = False,
        mouse_x = 0,
        mouse_y = 0,
        nearest = None,
        bseg = (0.0, None, 0, 0),
        beat_position = None,
        bu_split = None,
    )
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        beatline = comp.parent.parent.layout.inner
        graph = comp.parent
        x, y = comp.local_point(x, y)
        this.mouse_x = x
        this.mouse_y = y
        if not this.voice_lock:
            this.nearest = beatline.nearest_voice(graph, x, y)
        this.beat_position = beatline.location_as_position(graph, x, y)
        
        if this.nearest is not None:
            voice = beatline.get_voice(this.nearest[0])
            x1 = beatline.offsets[0]
            beat = 0.0
            for seg in voice.segments:
                x0 = resolution.sequence_interpolation(beat, beatline.beats, beatline.offsets, True)
                x1 = resolution.sequence_interpolation(beat + float(seg.duration), beatline.beats, beatline.offsets, True)
                if x0 < this.mouse_x <= x1:
                    this.bseg = beat, seg, x0, x1
                beat += float(seg.duration)
            if x1 <= this.mouse_x:
                this.bseg = beat, None, x1, graph.shape.width
        if this.bseg[2] < this.bseg[3]:
            if this.bseg[1] is not None:
                t = (this.mouse_x - this.bseg[2]) / (this.bseg[3] - this.bseg[2])
                bu = entities.by_beat(graph.layout.smeared, this.bseg[0]).beat_unit
                total = this.bseg[1].duration
                a = resolution.quantize(t * float(total), bu, (-7,1,3))
                b = total - a
                if b in resolution.valid_durations((-7,1,3)):
                    this.bu_split = (bu, a/bu, b/bu, this.bseg[1])
            else:
                bu = entities.by_beat(graph.layout.smeared, this.bseg[0]).beat_unit
                a = resolution.quantize((this.mouse_x - this.bseg[2]) / 50, bu, (-7,1,3))
                this.bu_split = (bu, a, None, None)

    @gui.listen(gui.e_leaving)
    def _leaving_(x, y):
        this.nearest = None
        this.bseg = (0, None, 0, 0)
        this.beat_position = None
        this.voice_lock = False

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        beatline = comp.parent.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            gui.inform(e_margin_press, comp, x, y, button)
        elif this.beat_position and this.nearest is not None:
            refbeat, position = this.beat_position
            if button == 3:
                this.voice_lock = not this.voice_lock
            if button == 1 and this.bu_split is not None and this.bu_split[3] == this.bseg[1]:
                bu, a, b, seg = this.bu_split
                if b is None:
                    voice = beatline.get_voice(this.nearest[0])
                    voice.segments.append(entities.VoiceSegment([], a * bu))
                else:
                    voice = beatline.get_voice(this.nearest[0])
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
        beatline = comp.parent.parent.layout.inner
        bb = comp.shape
        ctx = ui.ctx
        ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
        if this.voice_lock:
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
        if this.nearest is not None:
            staff_uid, dynamics_uid, xs, ys = beatline.trajectories[this.nearest[0]]
            for i, (x,y) in enumerate(zip(xs, ys)):
                if i == 0:
                    ctx.move_to(x, bb.y + y)
                else:
                    ctx.line_to(x, bb.y + y)
            ctx.stroke()
        if this.bseg[3] > this.bseg[2]:
            beat, seg, x0, x2 = this.bseg
            x1 = max(x0, this.mouse_x)
            staff_uid, dynamics_uid, xs, ys = beatline.trajectories[this.nearest[0]]
            ctx.set_source_rgba(1.0, 0.0, 1.0, 0.75)
            y0 = resolution.sequence_interpolation(x0, xs, ys)
            y1 = resolution.sequence_interpolation(x1, xs, ys)
            y2 = resolution.sequence_interpolation(x2, xs, ys)
            ctx.move_to(x0, bb.y + y0 + 5)
            ctx.line_to(x1, bb.y + y1 + 5)
            ctx.line_to(x1, bb.y + y1 - 30)
            ctx.line_to(x0, bb.y + y0 - 30)
            ctx.fill()
            ctx.set_source_rgba(1.0, 1.0, 0.0, 0.75)
            ctx.move_to(x1, bb.y + y1 + 5)
            ctx.line_to(x2, bb.y + y2 + 5)
            ctx.line_to(x2, bb.y + y2 - 30)
            ctx.line_to(x1, bb.y + y1 - 30)
            ctx.fill()
        if this.bu_split is not None and this.bu_split[3] == this.bseg[1]:
            ctx.set_source_rgba(0,0,0,1)
            beat, seg, x0, x2 = this.bseg
            bu, a, b, seg = this.bu_split
            level = this.mouse_y
            tab = {
                +1: chr(119132),
                +0: chr(119133),
                -1: chr(119134),
                -2: chr(119135),
                -3: chr(119136),
                -4: chr(119137),
                -5: chr(119138),
                -6: chr(119139),
                -7: chr(119140),
            }
            ctx.set_font_size(25)
            cat, n, k, flex = resolution.flexible_categorize(a*bu, bu, (-7,1,3))
            if cat == 'dotted':
                text = tab[n] + '.'*k
                ctx.set_font_size(12)
                ctx.move_to(x0 + 5, level)
                ctx.show_text(text)
            elif cat == 'fragment':
                text = tab[n]
                ctx.set_font_size(12)
                ctx.move_to(x0 + 5, level)
                ctx.show_text(text)
                ctx.move_to(x0 + 5, level + 12)
                ctx.show_text(str(k))
            elif cat == 'repeated':
                text = tab[n] + '*' + str(k)
                ctx.set_font_size(12)
                ctx.move_to(x0 + 5, level)
                ctx.show_text(text)
            ctx.set_font_size(25)
            if b is not None:
                cat, n, k, flex = resolution.flexible_categorize(b*bu, bu, (-7,1,3))
                if cat == 'dotted':
                    text = tab[n] + '.'*k
                    ctx.set_font_size(12)
                    ctx.move_to(x2 + 5, level)
                    ctx.show_text(text)
                elif cat == 'fragment':
                    text = tab[n]
                    ctx.set_font_size(12)
                    ctx.move_to(x2 + 5, level)
                    ctx.show_text(text)
                    ctx.move_to(x2 + 5, level + 12)
                    ctx.show_text(str(k))
                elif cat == 'repeated':
                    text = tab[n] + '*' + str(k)
                    ctx.set_font_size(12)
                    ctx.move_to(x2 + 5, level)
                    ctx.show_text(text)

split_tool = {'staff': staff_split_tool}

@gui.composable
def staff_input_tool(editor, instrument_uid):
    comp = gui.current_composition.get()
    gui.layout(gui.DynamicLayout())
    first_voice_uid = None
    first_beat = 0.0
    first_index = 0
    staff_uid = comp.parent.layout.uid
    for voice in comp.parent.parent.layout.inner.track.voices:
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
        cat = 'dotted',
        base = 0,
        dots = 0,
        tuplet = 3,
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
        beatline = comp.parent.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            gui.inform(e_margin_press, comp, x, y, button)
        else:
            x, y = comp.local_point(x, y)
            if button == 1:
                beatpoint = resolution.sequence_interpolation(x, beatline.offsets, beatline.beats)
                nearest = beatline.nearest_voice(comp.parent, x, y)
                if nearest is not None:
                    this.voice_uid = nearest[0]
                else:
                    this.voice_uid = None

                if this.voice_uid is not None:
                    voice = beatline.get_voice(this.voice_uid)
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
        layout = comp.parent.layout
        track = comp.parent.parent.layout.inner.track
        if this.voice_uid is None:
            uid = editor.document.next_uid()
            track.voices.append(entities.Voice(uid, layout.staff.uid, None, []))
            this.voice_uid = uid
            this.seg_index = 0
        block = entities.by_beat(layout.smeared, this.beat)
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
                    plugin.push_midi_event(buf, [0x91, m, 127])
            block = entities.by_beat(layout.smeared, this.beat)
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

        if key == sdl2.SDLK_a and this.base > -7:
            this.base -= 1

        if key == sdl2.SDLK_w and this.base < 1:
            this.base += 1

        if key == sdl2.SDLK_z and this.dots > 0 and this.cat == 'dotted':
            this.dots -= 1

        if key == sdl2.SDLK_x and this.dots < 3 and this.cat == 'dotted':
            this.dots += 1

        if key == sdl2.SDLK_z and this.cat == 'fragment':
            primes = [3,5,7,11]
            this.tuplet = primes[primes.index(this.tuplet) - 1]

        if key == sdl2.SDLK_x and this.cat == 'fragment':
            primes = [3,5,7,11,3]
            this.tuplet = primes[primes.index(this.tuplet) + 1]

        if key == sdl2.SDLK_e and this.cat == 'dotted':
            this.cat = 'fragment'
        elif key == sdl2.SDLK_e and this.cat == 'fragment':
            this.cat = 'dotted'
            
        if key == sdl2.SDLK_s:
            this.stencil = []

        if key == sdl2.SDLK_BACKSPACE:
            for voice in track.voices:
                if this.voice_uid == voice.uid and this.seg_index > 0:
                    seg = voice.segments[this.seg_index-1]
                    voice.segments[this.seg_index-1:this.seg_index] = []
                    this.seg_index -= 1
                    this.beat -= float(seg.duration)
            this._composition.set_dirty()

        if this.cat == 'dotted':
            duration = resolution.rebuild_duration(this.cat, this.base, this.dots) * block.beat_unit
        if this.cat == 'fragment':
            duration = resolution.rebuild_duration(this.cat, this.base, this.tuplet) * block.beat_unit
        seg = entities.VoiceSegment(
            notes = list(this.stencil),
            duration = duration
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
                    plugin.push_midi_event(buf, [0x81, m, 127])
            for m, plugin in this.playing:
                midi_event(m, plugin)
        if key == sdl2.SDLK_q:
            this.time_start = None

    @gui.drawing
    def _draw_(ui, comp):
        beatline = comp.parent.parent.layout.inner
        layout = comp.parent.layout
        ctx = ui.ctx
        bb = comp.shape
        if ui.focus == comp.uid:
            if this.voice_uid is None:
                ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
            else:
                ctx.set_source_rgba(0.0, 1.0, 0.0, 1.0)
            x = resolution.sequence_interpolation(this.beat, beatline.beats, beatline.offsets, True)
            y0 = layout.top_line
            y1 = layout.bot_line
            ctx.move_to(x,bb.y + y0 - 20)
            ctx.line_to(x,bb.y + y1 + 20)
            ctx.stroke()

            for note in this.stencil:
                ctx.set_source_rgba(*beatline.instrument_colors.get(note.instrument_uid, (0.25,0.25,0.25,1.0)))
                pitch = note.pitch
                y = layout.note_position(this.beat, pitch.position)
                ctx.arc(x, bb.y + y, 5, 0, math.pi*2)
                ctx.fill()
                if pitch.accidental is not None:
                    ctx.set_font_size(25)
                    xt = ctx.text_extents(resolution.char_accidental[pitch.accidental])
                    ctx.move_to(x - 8 - xt.width, bb.y + y + 5)
                    ctx.show_text(resolution.char_accidental[pitch.accidental])

            ctx.set_font_size(10)
            ctx.set_source_rgba(0.0, 0.0, 1.0, 1.0)
            ctx.move_to(x + 10, bb.y + y0 - 10)
            if this.accidental is not None:
                ctx.show_text(resolution.char_accidental[this.accidental])

            tab = {
                +1: chr(119132),
                +0: chr(119133),
                -1: chr(119134),
                -2: chr(119135),
                -3: chr(119136),
                -4: chr(119137),
                -5: chr(119138),
                -6: chr(119139),
                -7: chr(119140),
            }
            ctx.set_font_size(25)
            block = entities.by_beat(layout.smeared, this.beat)
            ctx.move_to(x + 15, bb.y + bb.height - 10)
            if this.cat == 'dotted':
                text = tab[this.base] + '.'*this.dots
            if this.cat == 'fragment':
                text = tab[this.base] + str(this.tuplet)
            ctx.show_text(text)

@gui.composable
def envelope_input_tool(editor, instrument_uid):
    comp = gui.current_composition.get()
    gui.layout(gui.DynamicLayout())
    this = gui.lazybundle(
        document = editor.document,
        seg_index = 0,
        beat = 0.0,
        tapped = random.randint(10, 200),
        taps = [],
        cat = 'dotted',
        base = 0,
        dots = 0,
        tuplet = 3,
    )
    if this.document != editor.document:
        this.seg_index = 0
        this.beat = 0
        this.tapped = random.randint(10, 200)
        this.taps = []
    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        beatline = comp.parent.parent.layout.inner
        layout = comp.parent.layout
        if comp.local_point(x, y)[0] < beatline.x0:
            gui.inform(e_margin_press, comp, x, y, button)
        else:
            x, y = comp.local_point(x, y)
            if button == 1:
                beatpoint = resolution.sequence_interpolation(x, beatline.offsets, beatline.beats)
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
        layout = comp.parent.layout
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
        if this.cat == 'dotted':
            duration = resolution.rebuild_duration(this.cat, this.base, this.dots) * 4
        if this.cat == 'fragment':
            duration = resolution.rebuild_duration(this.cat, this.base, this.tuplet) * 4
        if control is not None:
            seg = entities.EnvelopeSegment(control, value, duration)
            layout.envelope.segments[this.seg_index:this.seg_index] = [seg]
            this.seg_index += 1
            this.beat += float(seg.duration)
            this._composition.set_dirty()
    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        layout = comp.parent.layout
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

        if key == sdl2.SDLK_a and this.base > -7:
            this.base -= 1

        if key == sdl2.SDLK_w and this.base < 1:
            this.base += 1

        if key == sdl2.SDLK_z and this.dots > 0 and this.cat == 'dotted':
            this.dots -= 1

        if key == sdl2.SDLK_x and this.dots < 3 and this.cat == 'dotted':
            this.dots += 1

        if key == sdl2.SDLK_z and this.cat == 'fragment':
            primes = [3,5,7,11]
            this.tuplet = primes[primes.index(this.tuplet) - 1]

        if key == sdl2.SDLK_x and this.cat == 'fragment':
            primes = [3,5,7,11,3]
            this.tuplet = primes[primes.index(this.tuplet) + 1]

        if key == sdl2.SDLK_e and this.cat == 'dotted':
            this.cat = 'fragment'
        elif key == sdl2.SDLK_e and this.cat == 'fragment':
            this.cat = 'dotted'

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
        beatline = comp.parent.parent.layout.inner
        layout = comp.parent.layout
        bb = comp.shape
        ctx = ui.ctx
        if ui.focus == comp.uid:
            ctx.set_source_rgba(0,0,0,1)
            x = resolution.sequence_interpolation(this.beat, beatline.beats, beatline.offsets, True)
            ctx.move_to(x,bb.y)
            ctx.line_to(x,bb.y+bb.height)
            ctx.stroke()

            tab = {
                +1: chr(119132),
                +0: chr(119133),
                -1: chr(119134),
                -2: chr(119135),
                -3: chr(119136),
                -4: chr(119137),
                -5: chr(119138),
                -6: chr(119139),
                -7: chr(119140),
            }
            ctx.set_font_size(25)
            ctx.move_to(x + 15, bb.y + bb.height - 10)
            if this.cat == 'dotted':
                text = tab[this.base] + '.'*this.dots
            if this.cat == 'fragment':
                text = tab[this.base] + str(this.tuplet)
            ctx.show_text(text)

            if layout.envelope.kind == 'tempo':
                ctx.set_font_size(12)
                ctx.move_to(x + 35, bb.y - 15)
                ctx.show_text(str(this.tapped))

@gui.composable
def chord_progression_input_tool(editor, instrument_uid):
    comp = gui.current_composition.get()
    gui.layout(gui.DynamicLayout())
    this = gui.lazybundle(
        document = editor.document,
        seg_index = 0,
        beat = 0.0,
        cat = 'dotted',
        base = 0,
        dots = 0,
        tuplet = 3,
    )
    if this.document != editor.document:
        this.seg_index = 0
        this.beat = 0
    @gui.listen(gui.e_button_down)
    def _button_down_(x, y, button):
        layout = comp.parent.layout
        beatline = comp.parent.parent.layout.inner
        if comp.local_point(x, y)[0] < beatline.x0:
            gui.inform(e_margin_press, comp, x, y, button)
        else:
            x, y = comp.local_point(x, y)
            if button == 1:
                beatpoint = resolution.sequence_interpolation(x, beatline.offsets, beatline.beats)
                beat = 0.0
                i = 0
                for seg in layout.chord_progression.segments:
                    if beatpoint < beat + float(seg.duration) / 2:
                        break
                    beat += float(seg.duration)
                    i += 1
                this.beat = beat
                this.seg_index = i

    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        layout = comp.parent.layout

        if key == sdl2.SDLK_a and this.base > -7:
            this.base -= 1

        if key == sdl2.SDLK_w and this.base < 1:
            this.base += 1

        if key == sdl2.SDLK_z and this.dots > 0 and this.cat == 'dotted':
            this.dots -= 1

        if key == sdl2.SDLK_x and this.dots < 3 and this.cat == 'dotted':
            this.dots += 1

        if key == sdl2.SDLK_z and this.cat == 'fragment':
            primes = [3,5,7,11]
            this.tuplet = primes[primes.index(this.tuplet) - 1]

        if key == sdl2.SDLK_x and this.cat == 'fragment':
            primes = [3,5,7,11,3]
            this.tuplet = primes[primes.index(this.tuplet) + 1]

        if key == sdl2.SDLK_e and this.cat == 'dotted':
            this.cat = 'fragment'
        elif key == sdl2.SDLK_e and this.cat == 'fragment':
            this.cat = 'dotted'

        if key == sdl2.SDLK_BACKSPACE:
            if this.seg_index > 0:
                seg = layout.chord_progression.segments[this.seg_index-1]
                layout.chord_progression.segments[this.seg_index-1:this.seg_index] = []
                this.seg_index -= 1
                this.beat -= float(seg.duration)
                this._composition.set_dirty()
        nth = None
        if this.cat == 'dotted':
            duration = resolution.rebuild_duration(this.cat, this.base, this.dots) * 4
        if this.cat == 'fragment':
            duration = resolution.rebuild_duration(this.cat, this.base, this.tuplet) * 4
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
            layout.chord_progression.segments[this.seg_index:this.seg_index] = [seg]
            this.seg_index += 1
            this.beat += float(seg.duration)
            this._composition.set_dirty()
        if key == sdl2.SDLK_LEFT:
            if this.seg_index > 0:
                this.seg_index -= 1
                this.beat -= float(layout.chord_progression.segments[this.seg_index].duration)
        if key == sdl2.SDLK_RIGHT:
            if this.seg_index and this.seg_index < len(layout.chord_progression.segments):
                this.beat += float(layout.chord_progression.segments[this.seg_index].duration)
                this.seg_index += 1

    @gui.drawing
    def _draw_(ui, comp):
        beatline = comp.parent.parent.layout.inner
        layout = comp.parent.layout
        bb = comp.shape
        ctx = ui.ctx
        if ui.focus == comp.get_keys():
            ctx.set_source_rgba(0,0,0,1)
            x = resolution.sequence_interpolation(this.beat, beatline.beats, beatline.offsets, True)
            ctx.move_to(x,bb.y)
            ctx.line_to(x,bb.y+bb.height)
            ctx.stroke()

            tab = {
                +1: chr(119132),
                +0: chr(119133),
                -1: chr(119134),
                -2: chr(119135),
                -3: chr(119136),
                -4: chr(119137),
                -5: chr(119138),
                -6: chr(119139),
                -7: chr(119140),
            }
            ctx.set_font_size(25)
            ctx.move_to(x + 15, bb.y + bb.height - 10)
            if this.cat == 'dotted':
                text = tab[this.base] + '.'*this.dots
            if this.cat == 'fragment':
                text = tab[this.base] + str(this.tuplet)
            ctx.show_text(text)

input_tool = {
    'staff': staff_input_tool,
    'envelope': envelope_input_tool,
    'chord_progression': chord_progression_input_tool,
}

def block_width(block):
    width = 0
    if block.clef is not None:
         width += 50
    if block.canonical_key is not None:
         canon_key = block.canonical_key
         width += abs(canon_key) * 7
    if block.beats_in_measure is not None or block.beat_unit is not None:
         width += 30
    return width

# TODO: partition this into pieces.
def staff_block(ctx, layout, x0, y0, block, smear):
    ctx.save()
    ctx.translate(x0, y0)
    staff = layout.staff
    x = 0
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
            for y in layout.center_lines():
                ctx.move_to(x + 10, y-2)
                ctx.show_text(str(smear.beats_in_measure))
                ctx.move_to(x + 10, y+18)
                ctx.show_text(str(smear.beat_unit))
            x += 30
    ctx.restore()
    return x

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
                    if event.button.windowID == 0:
                        widgets = self.widgets.values()
                    else:
                        widgets = [self.widgets[event.button.windowID]]
                    for widget in widgets:
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
