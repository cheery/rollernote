import ctypes
import sdl2
import lilv
import numpy
import resolution
import math
import wave
import entities

class DeviceOutput:
    def __init__(self, transport, block_length=1024):
        self.transport = transport
        self.block_length = block_length
        self.audio_loop_c = sdl2.SDL_AudioCallback(self.audio_loop)
        wanted = sdl2.SDL_AudioSpec(44100, sdl2.AUDIO_F32, 2, self.block_length)
        wanted.callback = self.audio_loop_c
        wanted.userdata = None

        self.audio = sdl2.SDL_OpenAudio(ctypes.byref(wanted), None)
        sdl2.SDL_PauseAudio(0)

        self.chan0 = numpy.zeros(self.block_length, numpy.float32)
        self.chan1 = numpy.zeros(self.block_length, numpy.float32)

    def audio_loop(self, _, stream, length):
        now = sdl2.SDL_GetTicks64() / 1000.0
        self.chan0.fill(0)
        self.chan1.fill(0)
        self.transport.run(now, self.chan0, self.chan1)
        data = numpy.dstack([self.chan0, self.chan1]).flatten()
        ctypes.memmove(stream, data.ctypes.data, min(self.block_length*8, length))

    def close(self):
        sdl2.SDL_PauseAudio(1)

class WAVOutput:
    def __init__(self, transport, filename, block_length=1024):
        self.transport = transport
        self.filename = filename
        self.block_length = block_length
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

class Transport:
    def __init__(self, plugins, mutes):
        self.block_length = 1024
        self.mutes = mutes
        self.plugins = plugins
        self.time = 0.0
        self.live_voices = set()
        self.volume0 = 0.0
        self.volume1 = 0.0
        self.volume_meter = Meter()
        self.currently_playing = None
        self.loop = False
        self.play_start = None
        self.play_end   = None

    def play(self, bpm, voices, staves):
        self.currently_playing = bpm, voices, staves
        self.live_voices.update([
            LiveVoice(staves[voice.staff_uid], voice, bpm)
            for voice in voices
            if len(voice.segments) > 0
        ])

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
        return len(self.live_voices) == 0 and self.volume0 + self.volume1 == 0

    def run(self, now, audio0, audio1):
        mutelevel = min(self.mutes.get(uid, 0) for uid in self.plugins)
        mutelevel = min(0, mutelevel)
        for plugin in self.plugins.values():
            for e in plugin.pending_events:
                e()
            plugin.pending_events.clear()

        if len(self.live_voices) == 0 and self.loop and self.currently_playing:
            self.play(*self.currently_playing)
        elif len(self.live_voices) == 0 and not self.loop:
            self.currently_playing = None

        def get_mutelevel(lv):
            return self.mutes.get(lv.voice.staff_uid, 0)*2 + self.mutes.get(lv.voice.uid, 0)
        mutelevel2 = min(map(get_mutelevel, self.live_voices), default=0)
        mutelevel2 = min(0, mutelevel2)

        still_live = set()
        for lv in self.live_voices:
            if lv.current == -1: # new voice
                self.init_livevoice(lv, now)
                key = lv.get_key()
                if mutelevel2 == get_mutelevel(lv):
                    for note in lv.voice.segments[lv.current].notes:
                        if note.instrument_uid is None or mutelevel != self.mutes.get(note.instrument_uid, 0):
                            continue
                        plugin = self.plugins[note.instrument_uid]
                        buf = plugin.inputs['In']
                        mp = resolution.resolve_pitch(note.pitch, key)
                        plugin.push_midi_event(buf, [0x90, mp, 0xFF])
                        lv.live_notes.append((mp, plugin))
                still_live.add(lv)
            elif lv.next_vseg <= now:
                for mp, plugin in lv.live_notes:
                    buf = plugin.inputs['In']
                    plugin.push_midi_event(buf, [0x80, mp, 0xFF])
                lv.live_notes = []
                if lv.current + 1 < len(lv.voice.segments) and (self.play_end is None or lv.beat < self.play_end):
                    lv.last_vseg = lv.next_vseg
                    lv.last_beat = lv.beat
                    remaining = float(lv.voice.segments[lv.current+1].duration)
                    if self.play_end is not None:
                        remaining = min(remaining, self.play_end - lv.beat)
                    lv.beat += remaining
                    key = lv.get_key()
                    lv.next_vseg += lv.bpm.area(lv.last_beat, lv.beat - lv.last_beat, lambda bpm: 60 / bpm)
                    if mutelevel2 == get_mutelevel(lv):
                        for note in lv.voice.segments[lv.current+1].notes:
                            if note.instrument_uid is None or mutelevel != self.mutes.get(note.instrument_uid, 0):
                                continue
                            plugin = self.plugins[note.instrument_uid]
                            buf = plugin.inputs['In']
                            mp = resolution.resolve_pitch(note.pitch, key)
                            plugin.push_midi_event(buf, [0x90, mp, 0xFF])
                            lv.live_notes.append((mp, plugin))
                    still_live.add(lv)
                lv.current += 1
            else:
                still_live.add(lv)
        self.live_voices = still_live

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

class Meter:
    def __init__(self):
        self.volume0 = 0.0
        self.volume1 = 0.0
        self.clipping0 = False
        self.clipping1 = False
        self.decay = 0.95

class LinearEnvelope:
    def __init__(self, vector):
        self.vector = vector # vector consists of list of triples:
                             # position, constant, change rate

    def area(self, position, duration, f=lambda x: x):
        i = 0
        for j, (p, k0, k1) in enumerate(self.vector):
            if p <= position:
                i = j
        endpoint = position + duration
        accum = 0
        while i < len(self.vector) and self.vector[i][0] < endpoint:
            p, k0, k1 = self.vector[i]
            q = self.vector[i+1][0] if i+1 < len(self.vector) else endpoint
            x0 = max(p, position)
            x1 = min(q, endpoint)
            y0 = x0*k1 + k0
            y1 = x1*k1 + k0
            accum += (x1-x0)*f((y0+y1)/2)
            i += 1
        return accum

    def check_positiveness(self):
        p, k0, k1 = self.vector[0]
        positive = (p * k1 + k0) > 0
        
        for i, (p, h0, h1) in enumerate(self.vector):
            if i > 0:
                q, k0, k1 = self.vector[i-1]
                y = (p-q)*k1 + k0
                positive = positive and y > 0
        p, k0, k1 = self.vector[-1]
        positive = positive and k0 > 0 and k1 >= 0
        return positive

class LiveVoice:
    def __init__(self, staff, voice, bpm, beat=0.0, current=-1, next_vseg=0.0):
        self.smeared = entities.smear(staff.blocks)
        self.voice = voice
        self.bpm = bpm
        self.last_beat = beat
        self.beat = beat
        self.current = current
        self.last_vseg = next_vseg
        self.next_vseg = next_vseg
        self.live_notes = []

    def get_key(self):
        block = entities.by_beat(self.smeared, self.beat)
        return resolution.canon_key(block.canonical_key)
