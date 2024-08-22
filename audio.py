import ctypes
import sdl2
import lilv
import numpy
import resolution
import math

class Transport:
    def __init__(self, plugins):
        self.block_length = 1024
        self.plugins = plugins
        self.time = 0.0
        self.live_voices = set()

        self.volume_meter = Meter()

        self.audio_loop_c = sdl2.SDL_AudioCallback(self.audio_loop)
        wanted = sdl2.SDL_AudioSpec(48000, sdl2.AUDIO_F32, 2, self.block_length)
        wanted.callback = self.audio_loop_c
        wanted.userdata = None

        self.audio = sdl2.SDL_OpenAudio(ctypes.byref(wanted), None)
        sdl2.SDL_PauseAudio(0)

    def audio_loop(self, _, stream, length):
        plugins = list(self.plugins.plugins)
        for plugin in plugins:
            for e in plugin.pending_events:
                e()
            plugin.pending_events.clear()
        now = sdl2.SDL_GetTicks64() / 1000.0

        still_live = set()
        for lv in self.live_voices:
            buf = lv.plugin.inputs['In']
            if lv.current == -1: # new voice
                lv.current = 0
                lv.next_vseg = now + lv.bpm.area(lv.beat,
                                                 float(lv.voice[0].duration),
                                                 lambda bpm: 60 / bpm)
                lv.beat += float(lv.voice[0].duration)
                for note in lv.voice[0].notes:
                    mp = resolution.resolve_pitch(note)
                    lv.plugin.push_midi_event(buf, [0x90, mp, 0xFF])
                    lv.live_notes.append(mp)
                still_live.add(lv)
            elif lv.next_vseg <= now:
                for mp in lv.live_notes:
                    lv.plugin.push_midi_event(buf, [0x80, mp, 0xFF])
                lv.live_notes = []
                if lv.current + 1 < len(lv.voice):
                    lv.next_vseg += lv.bpm.area(lv.beat,
                                                float(lv.voice[lv.current+1].duration),
                                                lambda bpm: 60 / bpm)
                    lv.beat += float(lv.voice[lv.current+1].duration)
                    for note in lv.voice[lv.current+1].notes:
                        mp = resolution.resolve_pitch(note)
                        lv.plugin.push_midi_event(buf, [0x90, mp, 0xFF])
                        lv.live_notes.append(mp)
                    still_live.add(lv)
                lv.current += 1
            else:
                still_live.add(lv)

        audio0 = numpy.zeros(self.block_length, numpy.float32)
        audio1 = numpy.zeros(self.block_length, numpy.float32)
        for plugin in plugins:
            plugin.instance.run(self.block_length)
            audio0 += plugin.audio_outputs[0][1]
            audio1 += plugin.audio_outputs[1][1]

        meter = self.volume_meter
        r0 = math.sqrt(sum(audio0*audio0) / self.block_length)
        r1 = math.sqrt(sum(audio1*audio1) / self.block_length)
        meter.volume0 = max(r0, meter.volume0*meter.decay)
        meter.volume1 = max(r1, meter.volume1*meter.decay)
        meter.clipping0 = meter.clipping0 or max(abs(audio0)) > 1.0
        meter.clipping1 = meter.clipping1 or max(abs(audio1)) > 1.0

        data = numpy.dstack([audio0, audio1]).flatten()
        ctypes.memmove(stream, data.ctypes.data, min(self.block_length*8, length))

        for plugin in plugins:
            for data in plugin.inputs.values():
                seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
                seq[0].atom.size = 8
                #seq[0].atom.type = plugin.get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
                #seq[0].body.unit = plugin.get_urid('https://lv2plug.in/ns/ext/time#beat')
                #seq[0].body.pad  = 0

        self.time = now

    def close(self):
        sdl2.SDL_PauseAudio(1)

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
    def __init__(self, plugin, voice, bpm, beat=0.0, current=-1, next_vseg=0.0):
        self.plugin = plugin
        self.voice = voice
        self.bpm = bpm
        self.beat = beat
        self.current = current
        self.next_vseg = next_vseg
        self.live_notes = []
