import ctypes
import sdl2
import lilv
import numpy
import resolution
import math
import wave
import entities
import bisect

# class InstrumentState(ctypes.Structure):
#     _fields_ = [
#         ('run', ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint)),
#         ('handle', ctypes.c_void_p),
#         ('output0', ctypes.c_void_p),
#         ('output1', ctypes.c_void_p),
#         ('input', ctypes.c_void_p),
#         ('keyboard', ctypes.ARRAY(ctypes.c_uint, 4)),
#         ('keyboard_pending', ctypes.ARRAY(ctypes.c_uint, 4)),
#         ('MIDI_Event', ctypes.c_uint),
#     ]
# 
# class TransportState(ctypes.Structure):
#     _fields_ = [
#         ('sample_rate', ctypes.c_int),
#         ('block_length', ctypes.c_int),
#         ('now', ctypes.c_double),
#         ('instruments', ctypes.POINTER(InstrumentState)),
#     ]
# 
# audio_loop = ctypes.CDLL('./audio_loop.so')

class DeviceOutput:
    def __init__(self, transport):
        self.transport = transport
        self.block_length = transport.block_length
        self.audio_loop_c = sdl2.SDL_AudioCallback(self.audio_loop)
        wanted = sdl2.SDL_AudioSpec(44100, sdl2.AUDIO_F32, 2, self.block_length)
        wanted.callback = self.audio_loop_c
        wanted.userdata = None

        #wanted = sdl2.SDL_AudioSpec(44100, sdl2.AUDIO_F32, 2, self.block_length)
        #wanted.callback = ctypes.cast(audio_loop.audio_loop, sdl2.SDL_AudioCallback)
        #wanted.userdata = ctypes.cast(ctypes.pointer(self.transport.state), ctypes.c_void_p)

        self.audio = sdl2.SDL_OpenAudio(ctypes.byref(wanted), None)
        sdl2.SDL_PauseAudio(0)

        self.chan0 = numpy.zeros(self.block_length, numpy.float32)
        self.chan1 = numpy.zeros(self.block_length, numpy.float32)
        self.now = 0.0

    def audio_loop(self, _, stream, length):
        self.chan0.fill(0)
        self.chan1.fill(0)
        self.transport.run(self.now, self.chan0, self.chan1)
        data = numpy.dstack([self.chan0, self.chan1]).flatten()
        ctypes.memmove(stream, data.ctypes.data, min(self.block_length*8, length))
        self.now += self.block_length / 44100

    def close(self):
        sdl2.SDL_PauseAudio(1)

class WAVOutput:
    def __init__(self, transport, filename, block_length=1024):
        self.transport = transport
        self.filename = filename
        self.block_length = transport.block_length
        self.file = wave.open(filename, 'w')
        self.file.setnchannels(2)
        self.file.setsampwidth(2) # 16-bit
        self.file.setframerate(44100)
        self.time = 0.0
        self.chan0 = numpy.zeros(self.block_length, numpy.float32)
        self.chan1 = numpy.zeros(self.block_length, numpy.float32)

    def write_frame(self):
        self.chan0.fill(0)
        self.chan1.fill(0)
        self.transport.run(self.time, self.chan0, self.chan1)
        #stereo_wave = np.vstack((sine_wave_left, sine_wave_right)).T
        data = numpy.dstack([self.chan0, self.chan1]).flatten()
        data = (data * 32767).astype(numpy.int16) # To 16-bit PCM format
        self.file.writeframes(data.tobytes())
        self.time += self.block_length / 44100

    def close(self):
        self.file.close()

def get_dyn(envelope):
    if envelope is None:
        return resolution.LinearEnvelope([(0.0, 1.0, 0.0)])
    return resolution.linear_envelope(envelope.segments, default=1.0)

class Transport:
    def __init__(self, plugins, mutes, block_length):
        self.block_length = block_length
        self.mutes = mutes
        self.plugins = plugins
        self.time = 0.0
        #self.live_voices = set()
        self.volume0 = 0.0
        self.volume1 = 0.0
        self.volume_meter = Meter()
        #self.currently_playing = None
        self.loop = False
        self.play_start = None
        self.play_end   = None

        # ins = []
        # for uid, plugin in plugins.items():
        #     ins.append(InstrumentState(
        #        run = plugin.instance.get_descriptor().run,
        #        handle = plugin.instance.get_handle(),
        #        output0 = plugin.audio_outputs[0][1].ctypes.data,
        #        output1 = plugin.audio_outputs[1][1].ctypes.data,
        #        input = ctypes.cast(plugin.inputs['In'], ctypes.c_void_p),
        #        MIDI_Event = plugin.MIDI_Event))
        #        
        # self.instruments = (InstrumentState*(len(ins)+1))(*ins)
        # self.state = TransportState(
        #     sample_rate = 44100,
        #     block_length = self.block_length,
        #     now = 0.0,
        #     instruments = self.instruments)

        # EXHIBIT A
        self.keyboard = {}
        self.keyboard_pressed = {}
        self.keyboard_offset = {}
        self.keyboard_onset = {}
        self.velocities = {}
        for uid in plugins:
            self.keyboard[uid] = 0
            self.keyboard_pressed[uid] = 0
            self.keyboard_offset[uid] = 0
            self.keyboard_onset[uid] = 0
            self.velocities[uid] = [127]*128

        self.events = []
        self.eventi = 0
        self.last_event = 0.0

        self.offset = (0,0)

        self.playing = False
        self.begin = 0.0
        self.end = 0.0
        self.bpm = None
        self.beat = 0.0

    def play(self, bpm, voices, graphs):
        # EXHIBIT B
        self.refresh_events(bpm, voices, graphs)
        self.playing = True
        self.update_loop()
        self.beat = 0 if self.play_start is None else self.play_start
        self.begin = self.time - self.offset[0]
        self.end = self.offset[1] + self.begin

    def refresh_events(self, bpm, voices, graphs):
        def get_mutelevel(voice):
            return self.mutes.get(voice.staff_uid, 0)*2 + self.mutes.get(voice.uid, 0)
        mutelevel = min(map(get_mutelevel, voices), default=0)
        mutelevel = min(0, mutelevel)

        events = []
        def insert_event(t, evt):
            bisect.insort(events, (t, evt), key = lambda x: x[0])

        last_beat = 0.0
        for graph in graphs.values():
            if not isinstance(graph, entities.Staff):
                continue
            dyn = get_dyn(graphs.get(None))
            smeared = entities.smear(graph.blocks)
            for note in graph.notes:
                p0 = float(note.position)
                p1 = float(note.position) + float(note.duration)
                block = entities.by_beat(smeared, p0)
                key = resolution.canon_key(block.canonical_key)
                m = resolution.resolve_pitch(note.pitch, key)
                t0 = bpm.beat_to_time(p0)
                t1 = bpm.beat_to_time(p1)
                if note.timbre is not None:
                    insert_event(t0, ('note-on',  note.timbre, m, round(127 * dyn.value(p0))))
                    insert_event(t1, ('note-off', note.timbre, m, 127))
                last_beat = max(last_beat, p1)

        for voice in voices:
            if mutelevel != get_mutelevel(voice):
                continue
            smeared = entities.smear(graphs[voice.staff_uid].blocks)
            beat = 0.0
            dyn = get_dyn(graphs.get(voice.dynamics_uid))
            for seg in voice.segments:
                block = entities.by_beat(smeared, beat)
                key = resolution.canon_key(block.canonical_key)
                t0 = bpm.beat_to_time(beat)
                t1 = bpm.beat_to_time(beat + float(seg.duration))
                for note in seg.notes:
                    if note.instrument_uid is None:
                        continue
                    m = resolution.resolve_pitch(note.pitch, key)
                    insert_event(t0, ('note-on',  note.instrument_uid, m, round(127 * dyn.value(beat))))
                    insert_event(t1, ('note-off', note.instrument_uid, m, 127))
                beat += float(seg.duration)
                last_beat = max(last_beat, t1)
        self.last_event = last_beat
        self.events = events
        self.eventi = 0
        for uid in self.keyboard_pressed:
            self.keyboard_pressed[uid] = 0
        if self.bpm is not None:
            time = bpm.beat_to_time(self.beat)
            self.begin = self.time - time
            self.end = self.offset[1] + self.begin
        self.bpm = bpm

    def update_loop(self):
        if self.playing:
            if self.play_start is not None:
                t0 = self.bpm.beat_to_time(self.play_start)
            else:
                t0 = 0
            if self.play_end is not None:
                t1 = self.bpm.beat_to_time(self.play_end)
            else:
                t1 = self.bpm.beat_to_time(self.last_event)
            self.offset = t0, t1
            self.end = self.offset[1] + self.begin

    def init_livevoice(self, lv, now):
        vseg = now
        beat = 0.0
        start = self.play_start or 0.0
        for i, seg in enumerate(lv.voice.segments):
            if beat <= start < beat + float(seg.duration):
                break
            beat += float(seg.duration)
        offset = start - beat
        remaining = float(seg.duration) - offset
        if self.play_end is not None:
            remaining = min(remaining, self.play_end - beat)
        lv.last_vseg = now
        lv.last_beat = lv.beat = start
        lv.current = i
        lv.next_vseg = now + lv.bpm.area(lv.beat, remaining, lambda bpm: 60 / bpm)
        lv.beat += remaining

    # We'd need better signaling from our plugins to tell whether they are idle or not.
    def is_idle(self):
        v = self.volume0 + self.volume1
        dbfs = 20 * math.log10(v) if v > 0 else 0
        return dbfs < -60 and not self.playing

    def run(self, now, audio0, audio1):
        for plugin in self.plugins.values():
            for e in plugin.pending_events:
                e()
            plugin.pending_events.clear()

        # EXHIBIT D
        if self.playing:
            while self.eventi < len(self.events):
                t, evt = self.events[self.eventi]
                if now - self.begin < t:
                    break
                if evt[0] == 'note-on':
                    _, uid, m, vel = evt
                    self.keyboard_pressed[uid] |= 1 << m
                    self.keyboard_onset[uid] |= 1 << m
                    self.velocities[uid][m] = vel
                elif evt[0] == 'note-off':
                    _, uid, m, vel = evt
                    self.keyboard_pressed[uid] &= ~(1 << m)
                    self.keyboard_offset[uid] |= 1 << m
                    self.velocities[uid][m] = vel
                self.eventi += 1
            if self.end <= now and self.loop:
                for uid in self.keyboard_pressed:
                    self.keyboard_pressed[uid] = 0
                self.flush_keyboard()
                self.begin = now - self.offset[0]
                self.end = self.offset[1] + self.begin
                self.eventi = 0
            elif self.end <= now:
                for uid in self.keyboard_pressed:
                    self.keyboard_pressed[uid] = 0
                self.playing = False
                
            self.beat = self.bpm.time_to_beat(now - self.begin)

        # mutelevel = min((self.mutes.get(uid, 0) for uid in self.plugins), default=0)
        # mutelevel = min(0, mutelevel)

        # if len(self.live_voices) == 0 and self.loop and self.currently_playing:
        #     self.play(*self.currently_playing)
        # elif len(self.live_voices) == 0 and not self.loop:
        #     self.currently_playing = None

        # def get_mutelevel(lv):
        #     return self.mutes.get(lv.voice.staff_uid, 0)*2 + self.mutes.get(lv.voice.uid, 0)
        # mutelevel2 = min(map(get_mutelevel, self.live_voices), default=0)
        # mutelevel2 = min(0, mutelevel2)

        # still_live = set()
        # for lv in self.live_voices:
        #     if lv.current == -1: # new voice
        #         self.init_livevoice(lv, now)
        #         key = lv.get_key()
        #         if mutelevel2 == get_mutelevel(lv):
        #             vel = round(127 * lv.dyn.value(lv.last_beat))
        #             for note in lv.voice.segments[lv.current].notes:
        #                 if note.instrument_uid is None or mutelevel != self.mutes.get(note.instrument_uid, 0):
        #                     continue
        #                 plugin = self.plugins[note.instrument_uid]
        #                 buf = plugin.inputs['In']
        #                 mp = resolution.resolve_pitch(note.pitch, key)
        #                 plugin.push_midi_event(buf, [0x90, mp, vel])
        #                 lv.live_notes.append((mp, plugin))
        #         still_live.add(lv)
        #     elif lv.next_vseg <= now:
        #         for mp, plugin in lv.live_notes:
        #             buf = plugin.inputs['In']
        #             plugin.push_midi_event(buf, [0x80, mp, 0x1F])
        #         lv.live_notes = []
        #         if lv.current + 1 < len(lv.voice.segments) and (self.play_end is None or lv.beat < self.play_end):
        #             lv.last_vseg = lv.next_vseg
        #             lv.last_beat = lv.beat
        #             remaining = float(lv.voice.segments[lv.current+1].duration)
        #             if self.play_end is not None:
        #                 remaining = min(remaining, self.play_end - lv.beat)
        #             lv.beat += remaining
        #             key = lv.get_key()
        #             lv.next_vseg += lv.bpm.area(lv.last_beat, lv.beat - lv.last_beat, lambda bpm: 60 / bpm)
        #             if mutelevel2 == get_mutelevel(lv):
        #                 vel = round(127 * lv.dyn.value(lv.last_beat))
        #                 for note in lv.voice.segments[lv.current+1].notes:
        #                     if note.instrument_uid is None or mutelevel != self.mutes.get(note.instrument_uid, 0):
        #                         continue
        #                     plugin = self.plugins[note.instrument_uid]
        #                     buf = plugin.inputs['In']
        #                     mp = resolution.resolve_pitch(note.pitch, key)
        #                     plugin.push_midi_event(buf, [0x90, mp, vel])
        #                     lv.live_notes.append((mp, plugin))
        #             still_live.add(lv)
        #         lv.current += 1
        #     else:
        #         still_live.add(lv)
        # self.live_voices = still_live

        # EXHIBIT C
        self.flush_keyboard()

        for plugin in self.plugins.values():
            plugin.instance.run(self.block_length)
            audio0 += plugin.audio_outputs[0][1]
            audio1 += plugin.audio_outputs[1][1]

        meter = self.volume_meter
        r0 = math.sqrt(sum(audio0*audio0) / self.block_length)
        r1 = math.sqrt(sum(audio1*audio1) / self.block_length)
        self.volume0 = r0
        self.volume1 = r1
        meter.volume0 = max(r0, meter.volume0*meter.decay)
        meter.volume1 = max(r1, meter.volume1*meter.decay)
        meter.clipping0 = meter.clipping0 or max(abs(audio0)) > 1.0
        meter.clipping1 = meter.clipping1 or max(abs(audio1)) > 1.0

        for plugin in self.plugins.values():
            for data in plugin.inputs.values():
                seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
                seq[0].atom.size = 8
                #seq[0].atom.type = plugin.get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
                #seq[0].body.unit = plugin.get_urid('https://lv2plug.in/ns/ext/time#beat')
                #seq[0].body.pad  = 0
        self.time = now

    def flush_keyboard(self):
        mutelevel = min((self.mutes.get(uid, 0) for uid in self.plugins), default=0)
        mutelevel = min(0, mutelevel)
        for uid, plugin in self.plugins.items():
            velocities = self.velocities[uid]
            buf = plugin.inputs['In']
            pressed = self.keyboard_pressed[uid]
            if mutelevel != self.mutes.get(uid, 0):
                pressed = 0
            delta = self.keyboard[uid] ^ pressed
            onset = (~self.keyboard_pressed[uid]) & self.keyboard_onset[uid]
            offset = self.keyboard_pressed[uid] & self.keyboard_offset[uid]
            for i in range(128):
                if (delta >> i) & 1:
                    if (pressed >> i) & 1:
                        plugin.push_midi_event(buf, [0x90, i, velocities[i]])
                    else:
                        plugin.push_midi_event(buf, [0x80, i, velocities[i]])
                elif (onset >> i) & 1:
                    plugin.push_midi_event(buf, [0x90, i, velocities[i]])
                    plugin.push_midi_event(buf, [0x80, i, velocities[i]])
                elif (offset >> i) & 1:
                    plugin.push_midi_event(buf, [0x80, i, velocities[i]])
                    plugin.push_midi_event(buf, [0x90, i, velocities[i]])
            self.keyboard[uid] = pressed
            self.keyboard_offset[uid] = 0
            self.keyboard_onset[uid] = 0

class Meter:
    def __init__(self):
        self.volume0 = 0.0
        self.volume1 = 0.0
        self.clipping0 = False
        self.clipping1 = False
        self.decay = 0.95

class LiveVoice:
    def __init__(self, staff, voice, bpm, dyn, beat=0.0, current=-1, next_vseg=0.0):
        self.smeared = entities.smear(staff.blocks)
        self.voice = voice
        self.bpm = bpm
        self.dyn = dyn
        assert dyn.check_positiveness(allow_zero=True)
        self.last_beat = beat
        self.beat = beat
        self.current = current
        self.last_vseg = next_vseg
        self.next_vseg = next_vseg
        self.live_notes = []

    def get_key(self):
        block = entities.by_beat(self.smeared, self.beat)
        return resolution.canon_key(block.canonical_key)
