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
        counter = 0,
        text = "foobar",
    )

    # Editor history
    history = editor.history

    undo = components.button(chr(0x21B6), font_size=24, disabled=len(history.undo_stack) == 0)
    undo.shape = gui.Box(100, 10, 32, 32)
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

    redo = components.button(chr(0x21B7), font_size=24, disabled=len(history.redo_stack) == 0)
    redo.shape = gui.Box(133, 10, 32, 32)
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
    @splitbutton.listen(gui.e_button_down)
    def _splitbutton_down_(x, y, button):
        this.tool = split_tool

    plotbutton = components.button("plot", font_size=32)
    plotbutton.shape = gui.Box(172+32*6, 52, 32*2, 32)
    @plotbutton.listen(gui.e_button_down)
    def _plotbutton_down_(x, y, button):
        this.tool = plot_tool

    meter = vu_meter(editor.transport.volume_meter)
    meter.shape = gui.Box(10, 10, 20, 90)

    openplugin = components.button(editor.plugin.name, font_size=10)
    openplugin.shape = gui.Box(10, 110, 80, 15)
    @openplugin.listen(gui.e_button_down)
    def _openplugin_down_(x, y, button):
        plugin = editor.plugin
        if plugin.widget is None:
            editor.widget(plugin.name, 120, 70, lv2.UIPayload, plugin)

    hmm = components.button(f"hello {this.counter}")
    hmm.shape = gui.Box(310, 22, 100, 20)
    @hmm.listen(gui.e_button_down)
    def _click_(x, y, button):
        this.counter += 1
    haa = components.textbox(this.text, gui.setter(this, 'text'))
    haa.shape = gui.Box(200, 22, 100, 20)

    document = editor.document
    layouts = {}
    y_base = 150
    for staff in document.track.graphs:
        layouts[staff.uid] = layout = StaffLayout(y_base, staff, document.track.voices)
        y_base += layout.height + 10
    beatline(layouts, document.track, this.tool)

    widget = gui.ui.get().widget
    components.label(this.status, 0, widget.height - 3)

    @gui.listen(gui.e_key_down)
    def _down_(key, repeat, modifier):
        if repeat == 0:
            @editor.plugin.event
            def _event_():
                buf = editor.plugin.inputs['In']
                editor.plugin.push_midi_event(buf, [0x91, key % 128, 0xFF])

    @gui.listen(gui.e_key_up)
    def _up_(key, modifier):
        @editor.plugin.event
        def _event_():
            buf = editor.plugin.inputs['In']
            editor.plugin.push_midi_event(buf, [0x81, key % 128, 0xFF])

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
                    for pitch in seg.notes:
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
       
@gui.composable
def beatline(layouts, track, tool_app):
    widget = gui.ui.get().widget
    gui.shape(gui.Box(0, 150, widget.width, widget.height - 170))
    this = gui.lazybundle(
        scroll_x_anchor = None,
        scroll_x = 0,
    )

    # Scrolling behavior
    @gui.listen(gui.e_motion)
    @gui.listen(gui.e_dragging)
    def _motion_(x, y):
        if this.scroll_x_anchor is not None:
            this.scroll_x += x - this.scroll_x_anchor
            this.scroll_x_anchor = x

    @gui.listen(gui.e_button_down)
    def _down_(x, y, button):
        this.scroll_x_anchor = x

    @gui.listen(gui.e_button_up)
    def _up_(x, y, button):
        this.scroll_x_anchor = None

    x0 = this.scroll_x + max(layout.left_margin for layout in layouts.values())

    @gui.drawing
    def _draw_(ui, comp):
        ctx = ui.ctx
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        for layout in layouts.values():
            # Staff lines
            # These are rendered without refering
            # to anything else but staff.top and staff.bot and margins
            for i in range(layout.start, layout.stop, 2):
                if i % 12 != 2:
                    k = i * 5
                    ctx.move_to(0, layout.y+k)
                    ctx.line_to(widget.width, layout.y+k)
                    ctx.stroke()

            initial = layout.by_beat(0.0)
            canon_key = initial.canonical_key
            key = resolution.canon_key(canon_key)

            # Major/Minor letters above the 'clef'
            major = resolution.tonic(canon_key)
            minor = resolution.tonic(canon_key, 5)
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
                block = layout.by_beat(0.0)
                staff_block(ctx, layout, x0 - layout.left_margin + 35, block, block)
                # bar
                ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                ctx.move_to(x0, layout.graph_point(layout.staff.top*12 - 1))
                ctx.line_to(x0, layout.graph_point(layout.staff.bot*12 + 3))
                ctx.stroke()

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
                note_position = mean(pitch.position for pitch in seg.notes)

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

    trajectories = []
    for voice in track.voices:
        trajectories.append((voice.staff_uid, voice.uid, [], []))

    last_beat = max((l.last_beat for l in layouts.values()), default=0.0)

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
        if which == E_SEGMENT:
            duration, seg, layout, voice = value
            tie = len(seg_xs.get(seg, []))
            segments.append((beat, x, tie, duration, seg, layout))
            if len(seg.notes) > 0:
                for staff_uid, voice_uid, xs, ys in trajectories:
                    if voice_uid == voice.uid:
                        p = mean(p.position for p in seg.notes)
                        y = layout.note_position(beat, p)
                        xs.append(x)
                        ys.append(y)
                    
            resolution.insert_in_list(seg_xs, seg, (beat, x))
    if beat < last_beat:
        x += q * (last_beat - beat) ** a
        offsets.append(x)
        beats.append(last_beat)
    for staff_uid, voice_uid, xs, ys in trajectories:
        if len(xs) == 0:
            xs.append(x0 + 20)
            ys.append(layout.y + layout.height // 2)
        

    @gui.drawing
    def _draw_lines_(ui, comp):
        ctx = ui.ctx
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

        ctx.set_source_rgba(1.0, 0.0, 0.0, 0.4)
        ctx.set_dash([4, 2])
        for _, voice_uid, xs, ys in trajectories:
            for i, (x,y) in enumerate(zip(xs, ys)):
                if i == 0:
                    ctx.move_to(x, y)
                else:
                    ctx.line_to(x, y)
            ctx.stroke()
        ctx.set_dash([])

        for beat, x, tie, duration, seg, layout in segments:
            ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
            block = layout.by_beat(beat)
            beat_unit = block.beat_unit
            cat = resolution.categorize_note_duration(duration / beat_unit)
            if cat is None:
                if len(seg.notes) == 0:
                    t = empty_segment_position[seg]
                else:
                    t = mean(pitch.position for pitch in seg.notes)
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
            for pitch in seg.notes:
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
            if len(seg.notes) > 0:
                high = min(layout.note_position(beat, p.position) for p in seg.notes)
                low = max(layout.note_position(beat, p.position) for p in seg.notes)
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
          graph_uid,
          layout,
          seg_xs,
          offsets,
          beats,
          trajectories,
          track,
        )

def location_as_position(layout, offsets, beats, x, y):
    beat = monotonic_interpolation(x, offsets, beats)
    clef = entities.by_beat(layout.smeared, beat).clef
    return beat, round((layout.reference - y) / 5) + layout.staff.bot*12 + clef

def nearest_voice(trajectories, ix, iy, current_staff_uid):
    closest = None
    closest_y = None
    closest_z = None
    distance = None
    for staff_uid, voice_uid, xs, ys in trajectories:
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
def plot_tool(staff_uid, layout, seg_xs, offsets, beats, trajectories, track):
    _ui = gui.ui.get()
    _comp = gui.current_composition.get()
    gui.shape(gui.Box(0, layout.y, _ui.widget.width, layout.height))

    voice_lock = gui.state(False)
    mouse_x = gui.state(0)
    mouse_y = gui.state(0)
    nearest = gui.state((None, None, None))
    beat_position = gui.state(None)
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        mouse_x.lazy(x)
        mouse_y.lazy(y)
        if not voice_lock.value:
            nearest.value = nearest_voice(trajectories, mouse_x.value, mouse_y.value, layout.staff.uid)
        for voice in track.voices:
            if voice.staff_uid != staff_uid and nearest.value[0] == voice.uid:
                nearest.value = (None, None, None)

        beat_position.value = location_as_position(
          layout, offsets, beats, mouse_x.value, mouse_y.value)
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
                if not any(pitch.position == position for pitch in seg.notes):
                    seg.notes.append(entities.Pitch(position))
                    _comp.set_dirty()
                    beat_position.value = None
            if button == 2 and seg is not None:
                for pitch in seg.notes:
                    if pitch.position == position:
                        seg.notes.remove(pitch)
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
        for staff_uid, voice_uid, xs, ys in trajectories:
            if nearest.value[0] == voice_uid:
                for i, (x,y) in enumerate(zip(xs, ys)):
                    if i == 0:
                        ctx.move_to(x, y)
                    else:
                        ctx.line_to(x, y)
                ctx.stroke()
        if beat_position.value:
            beat, position = beat_position.value
            x = mouse_x.value
            y = layout.note_position(beat, position)
            ctx.arc(x, y, 5, 0, 2*math.pi)
            ctx.fill()

@gui.composable
def split_tool(staff_uid, layout, seg_xs, offsets, beats, trajectories, track):
    _ui = gui.ui.get()
    gui.shape(gui.Box(0, layout.y, _ui.widget.width, layout.height))

    voice_lock = gui.state(False)
    mouse_x = gui.state(0)
    mouse_y = gui.state(0)
    nearest = gui.state((None, None, None))
    bseg = gui.state((0.0, None, 0, 0))
    beat_position = gui.state(None)
    bu_split = gui.state(None)
    @gui.listen(gui.e_motion)
    def _motion_(x, y):
        mouse_x.lazy(x)
        mouse_y.lazy(y)
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
        for staff_uid, voice_uid, xs, ys in trajectories:
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
            for staff_uid, voice_uid, xs, ys in trajectories:
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

if __name__=='__main__':
    Editor().ui()
