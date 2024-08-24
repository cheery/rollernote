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
from fractions import Fraction

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

        self.tool = SplittingTool(editor.document)

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
        ctx.rectangle(100, 20+32, 32, 32)
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
        ctx.rectangle(132+10, 20+32, 32*3, 32)
        ctx.stroke()
        ctx.move_to(132+10, 20+32+28)
        ctx.show_text("save")

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
        staff = document.track.graphs[0]
        assert isinstance(staff, entities.Staff)

        staff_blocks = entities.smear(staff.blocks)

        initial = entities.by_beat(staff_blocks, 0.0)
        beat_unit = initial.beat_unit
        beats_in_measure = initial.beats_in_measure
        canon_key = initial.canonical_key
        clef = initial.clef
        key = resolution.canon_key(canon_key)

        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)

        # Margins to fit everything in
        def shifted_positions():
            for voice in document.track.voices:
                beat = 0.0
                for seg in voice.segments:
                    block = entities.by_beat(staff_blocks, beat)
                    for pitch in seg.notes:
                        yield pitch.position - staff.bot*12 - block.clef
                    beat += float(seg.duration)
        positions = list(shifted_positions())
        margin_bot = staff.bot + min(min(positions) // 12, 0)
        margin_top = max(staff.top, staff.bot + (max(positions) // 12))

        # Staff lines
        # These are rendered without refering
        # to anything else but staff.top and staff.bot and margins
        start = (margin_top - staff.top)*12+2
        stop = (margin_top - staff.bot)*12+2
        for i in range(start, stop, 2):
            if i % 12 != 2:
                k = i * 5
                ctx.move_to(0, 150+k)
                ctx.line_to(self.renderer.widget.width, 150+k)
                ctx.stroke()
        span = (margin_top - margin_bot)*12+4
        height = span * 5
        ctx.set_source_rgba(0.5, 0.5, 1.0, 1.0)
        ctx.move_to(0, 150)
        ctx.line_to(self.renderer.widget.width, 150)
        ctx.move_to(0, 150+height)
        ctx.line_to(self.renderer.widget.width, 150+height)
        ctx.stroke()

        # The reference note is staff.bot*12-clef
        reference = (stop+1) * 5 + 150
        ctx.move_to(0, reference)
        ctx.line_to(self.renderer.widget.width, reference)
        ctx.stroke()

        def note_position(beat, position):
            clef = entities.by_beat(staff_blocks, beat).clef
            return reference - (position - staff.bot*12 - clef)*5

        # Major/Minor letters above the 'clef'
        major = resolution.tonic(canon_key)
        minor = resolution.tonic(canon_key, 5)
        major_text = resolution.pitch_name(major, key, show_octave=False)
        minor_text = resolution.pitch_name(minor, key, show_octave=False)
        ctx.set_font_size(10)
        ctx.move_to(35, 150 + 9)
        ctx.show_text(f"{major_text} {minor_text}m")

        # Initial pitch markings
        ctx.set_font_size(10)
        for i in range(0, span, 2):
            position = i + staff.bot*12 + clef
            t = resolution.pitch_name(entities.Pitch(position), key)
            ctx.move_to(10, note_position(0.0, position)+4)
            ctx.show_text(t)

        # Layout calculation begins
        x = 25

        def staff_block(block, full_block):
            nonlocal x

            if block.clef is not None:
                # Our version of a clef
                # Select most centered C, F, G in the staff
                ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
                ctx.set_font_size(20)
                i = (staff.top*6 + staff.bot*6) + block.clef + 1
                j = i - i % 7
                p = min((j + x for x in [-7, -4, -3, 0, 3, 4] if (j + x - block.clef) % 2 == 1),
                        key = lambda p: abs(p - i))
                y = note_position(block.beat, p)
                t = resolution.pitch_name(entities.Pitch(p))
                ctx.move_to(x + 15 + 7, y+7)
                ctx.show_text(t)
                ctx.arc(x + 15, y, 5, 0, 2*math.pi)
                ctx.fill()

                #ctx.arc(x + 15, note_position(block.beat, i), 5, 0, 2*math.pi)
                #ctx.fill()
                x += 50

            if block.canonical_key is not None:
                canon_key = block.canonical_key
                # Key signature
                ctx.set_font_size(25)
                # The vertical positioning of accidentals is awful at the moment,
                # but blame people who call you stupid when you ask
                # what is behind vertical positioning of accidentals.
                if canon_key >= 0:
                    for sharp in resolution.sharps[:canon_key]:
                        for i in range(staff.bot, staff.top):
                            position = i*12 + block.clef + 11
                            c_pos = position - position % 7
                            if c_pos + 4 >= position + 2:
                                j = c_pos + sharp - 7
                            else:
                                j = c_pos + sharp - 7 * (sharp > 4)
                            ctx.move_to(x, note_position(block.beat, j)+4)
                            ctx.show_text(resolution.char_accidental[1])
                        x += 7
                else:
                    for flat in reversed(resolution.sharps[canon_key:]):
                        for i in range(staff.bot, staff.top):
                            position = i*12 + block.clef + 11
                            j = (position - position % 7) + flat - 7 * (flat > 2)
                            # It is questionable to move them around like this,
                            # It seems that more likely there are several fixed patterns
                            # and one is used when it fits the best.
                            if j > position:
                                 j -= 7
                            if j <= position - 10:
                                 j += 7
                            ctx.move_to(x, note_position(block.beat, j)+4)
                            ctx.show_text(resolution.char_accidental[-1])
                        x += 7

            if block.beats_in_measure is not None or block.beat_unit is not None:
                ctx.set_source_rgba(0, 0, 0, 1)
                ctx.set_font_size(25)
                for i in range(staff.bot, staff.top):
                    position = i*12 + clef + 7
                    ctx.set_font_size(25)
                    ctx.move_to(x + 10, note_position(0, position)-2)
                    ctx.show_text(str(full_block.beats_in_measure))
                    ctx.move_to(x + 10, note_position(0, position)+18)
                    ctx.show_text(str(full_block.beat_unit))

            x += 30

        staff_block(initial, initial)

        # bar
        ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
        ctx.move_to(x, note_position(0.0, staff.top*12 + clef - 1))
        ctx.line_to(x, note_position(0.0, staff.bot*12 + clef + 3))
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
            for seg in reversed(voice.segments):
                if len(seg.notes) == 0:
                    if position is None:
                        positions = empty_segment_position[seg]
                        if len(positions) == 0:
                            positions.append((low_staff + high_staff)//2)
                    else:
                        empty_segment_position[seg].append(position)
                else:
                    position = mean(pitch.position for pitch in seg.notes)
            for seg in reversed(voice.segments):
                if len(seg.notes) == 0:
                    empty_segment_position[seg] = mean(empty_segment_position[seg])
        # Events on the line
        events = []
        E_SEGMENT = 0
        E_BARLINE = 1
        E_BLOCK = 2
        def insert_event(beat, kind, value):
            bisect.insort_left(events, (beat, kind, value), key=lambda k: k[0])
        # Breaking segments into measures
        def beats_in_this_measure(eat):
            this, future = entities.at_beat(staff_blocks, beat)
            if future is None:
                return this.beats_in_measure, False
            else:
                distance = future.beat - beat
                if distance < this.beats_in_measure:
                    return distance, True
                else:
                    return this.beats_in_measure, False
        measured_voices = []
        highest_beat = 0.0
        for voice in document.track.voices:
            measures = []
            measure = []
            beat = 0.0
            remain, _ = beats_in_this_measure(beat)
            for seg in voice.segments:
                duration = seg.duration
                while remain < duration:
                    if remain > 0:
                        insert_event(beat, E_SEGMENT, (remain, seg))
                        duration -= remain
                        beat += float(remain)
                        measure.append((remain, seg))
                    measures.append(measure)
                    remain, _ = beats_in_this_measure(beat)
                    measure = []
                if duration != 0: # seg.duration <= remain
                    insert_event(beat, E_SEGMENT, (duration, seg))
                    remain -= duration
                    beat += float(duration)
                    measure.append((duration, seg))
            highest_beat = max(highest_beat, beat)
            measures.append(measure)
            measured_voices.append(measures)
        def frange(start, stop, step):
            current = start
            while current < stop:
                yield current
                current += step
        # Inserting blocks into event stream
        previous = initial
        for i, block in enumerate(staff_blocks[1:], 1):
            for stop in frange(previous.beat + previous.beats_in_measure, block.beat, previous.beats_in_measure):
                insert_event(stop, E_BARLINE, None)
            rawblock = document.track.graphs[0].blocks[i]
            unusual = (block.beat - previous.beat) % previous.beats_in_measure != 0
            insert_event(block.beat, E_BLOCK, (rawblock, block, unusual))
            previous = block
        for stop in frange(previous.beat + previous.beats_in_measure, highest_beat, previous.beats_in_measure):
            insert_event(stop, E_BARLINE, None)

        # Layout data to draw ties
        layout = {}
        # Offsets and corresponding beat for drawing segment boxes
        offsets = [x]
        beats = [0.0]
        beat = 0.0
        # "Efficient algorithms for music engraving,
        #  focusing on correctness"
        for time, which, value in events:
            if beat < time:
                x += q * ((time - beat) / beat_unit) ** a
                beat = time
                offsets.append(x)
                beats.append(beat)
            if which == E_BLOCK:
                rawblock, block, unusual = value
                if unusual:
                    ctx.set_dash([1, 1])
                    ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                    ctx.move_to(x, note_position(0.0, staff.top*12 + clef - 1))
                    ctx.line_to(x, note_position(0.0, staff.bot*12 + clef + 3))
                    ctx.stroke()
                    ctx.stroke()
                    ctx.set_dash([])
                staff_block(rawblock, block)
                x += 10
                offsets.append(x)
                beats.append(beat)
            if which == E_BARLINE:
                ctx.set_source_rgba(0.5, 0.5, 0.5, 1.0)
                ctx.move_to(x, note_position(0.0, staff.top*12 + clef - 1))
                ctx.line_to(x, note_position(0.0, staff.bot*12 + clef + 3))
                ctx.stroke()
                x += 20
                offsets.append(x)
                beats.append(beat)
            if which == E_SEGMENT:
                ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
                duration, seg = value
                cat = resolution.categorize_note_duration(duration / beat_unit)
                if cat is None:
                    if len(seg.notes) == 0:
                        t = empty_segment_position[seg]
                    else:
                        t = mean(pitch.position for pitch in seg.notes)
                    t = (t - t % 12) - 6
                    k = (high_bound - t) * 5
                    ctx.set_font_size(10)
                    ctx.move_to(x - 4, 150 + k -2)
                    ctx.show_text(f'|{duration / beat_unit}|')
                    d = resolution.quantize_fraction(duration / beat_unit)
                    cat = resolution.categorize_note_duration(d)

                if True:
                    base, dots, triplet = cat
                    if len(seg.notes) == 0:
                        t = empty_segment_position[seg]
                        t = (t - t % 12) - 6
                        y = note_position(beat, t)
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
                        y = note_position(beat, pitch.position)
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
                            y0 = note_position(past, pitch.position)
                            ctx.move_to(px+8, y0 + 3)
                            ctx.curve_to(px+8, 8 + y0 + 3,
                                         x-8, 8 + y + 3,
                                         x-8, 0 + y + 3)
                            ctx.stroke()
                    if len(seg.notes) > 0:
                        high = min(note_position(beat, p.position) for p in seg.notes)
                        low = max(note_position(beat, p.position) for p in seg.notes)
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
        ctx.move_to(x, note_position(0.0, staff.top*12 + clef - 1))
        ctx.line_to(x, note_position(0.0, staff.bot*12 + clef + 3))
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

        def mk_cb(bb, beat, seg_index, spacing):
            def _hover_(x,y):
                return self.tool.hover_segment(bb, beat, seg_index, spacing, x, y)
            bb.on_hover = _hover_
            def _button_down_(x,y,button):
                return self.tool.button_down_segment(bb, beat, seg_index, spacing, x, y, button)
            bb.on_button_down = _button_down_

        voice = document.track.voices[0]
        beat = 0.0
        for index, seg in enumerate(voice.segments):
            duration = float(seg.duration)
            spacing = q * (duration / beat_unit) ** a
            left = monotonic_interpolation(beat, beats, offsets, use_highest=True)
            right = monotonic_interpolation(beat+duration, beats, offsets)
            right = max(right, left + spacing)
            #if beat <= self.loco < beat + duration:
            #    ctx.rectangle(left, 150, zzz-left, (high_bound - low_bound)*5 )
            #    ctx.stroke()
            low = note_position(0.0, staff.top*12 + clef - 1)
            high = note_position(0.0, staff.bot*12 + clef + 3)
            bb = gui.Box(left, low, right-left, high - low )
            mk_cb(bb, beat, index, spacing)
            hit.append(bb)
            beat += duration
        if right < self.renderer.widget.width:
            #if beat <= self.loco:
            #    ctx.rectangle(right, 150, self.renderer.widget.width - right, (high_bound - low_bound)*5)
            #    ctx.stroke()
            # On terminal segment, we give a spacing for a single beat and use it for letting user
            # subdivide the terminal segment and create new segments that way.
            spacing = q * (1.0 / beat_unit) ** a
            low = note_position(0.0, staff.top*12 + clef - 1)
            high = note_position(0.0, staff.bot*12 + clef + 3)
            bb = gui.Box(right, low, self.renderer.widget.width - right, high - low)
            mk_cb(bb, beat, -1, spacing)
            hit.append(bb)

        self.tool.draw(ctx, hit)
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

    def hover_segment(self, bb, beat, seg_index, spacing, x, y):
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
            total = self.document.track.voices[0].segments[self.split_index].duration / 4
            a = resolution.quantize_fraction(self.split_point * float(total))
            b = total - a
            if b in resolution.generate_all_note_durations():
                self.split = (a, b)
        else:
            a = resolution.quantize_fraction((x - bb.x) / spacing / 4)
            self.split = (a, None)
        return True

    def button_down_segment(self, bb, beat, seg_index, spacing, x, y, button):
        if self.split is not None:
            a, b = self.split
            if b is None:
                self.document.track.voices[0].segments.append(entities.VoiceSegment([], a * 4))
            else:
                n1 = list(self.document.track.voices[0].segments[self.split_index].notes)
                n2 = list(self.document.track.voices[0].segments[self.split_index].notes)
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

if __name__=='__main__':
    Editor().ui()
