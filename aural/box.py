import reaction
import math
import inspect
from collections import namedtuple
from reaction import *

class Bay:
    def __init__(self, event_engine, engine, locator, pulse):
        self.event_engine = event_engine
        self.engine = engine
        self.locator = locator
        self.pulse = pulse
        self.frame = 0

    def run(self):
        self.event_engine.send(self.pulse, self.frame)
        self.event_engine.step()
        self.frame += 1

class Patch(reaction.Flow):
    def __init__(self, bay, desc, connection, sources):
        super().__init__([bay.pulse] + sources)
        self.bay = bay
        self.desc = desc
        self.connection = connection
        self.patch = []
        outputs = {}
        for port in desc.info['ports']:
            try:
                i = connection.index(port['name'])
            except ValueError:
                assert port['type'] == 'input'
                hint = port['hint']
                default = hint['default']
                assert default
                value = default['value']
                if default['ratio']:
                    lower = hint['lower'] or 0.0
                    upper = hint['upper'] or 0.0
                    if hint['sample_rate']:
                        lower *= bay.engine.sample_rate
                        upper *= bay.engine.sample_rate
                    u = value
                    w = 1.0 - value
                    if hint['logarithmic']:
                        value = math.exp(math.log(lower) * u + math.log(upper) * w)
                    else:
                        value = lower * u + upper * w
                elif hint['sample_rate']:
                    value *= bay.engine.sample_rate
                ab = bay.engine.cell(value)
                self.patch.append((False, ab, None))
            else:
                if i < len(sources):
                    match port['type']:
                        case "input":
                            ab = bay.engine.cell(0.0)
                            mode = 0
                        case "input*":
                            ab = sources[i].value
                            mode = 1
                    self.patch.append((mode, ab, sources[i]))
                else:
                    match port['type']:
                        case "output":
                            acel = bay.engine.cell(0.0)
                            cell = reaction.Cell(0.0, [self])
                            self.patch.append((2, acel, cell))
                        case "output*":
                            buf = bay.engine.zeros()
                            cell = reaction.Cell(buf, [self])
                            self.patch.append((3, buf, cell))
                    outputs[port['name']] = cell
        self.outputs = []
        for name in connection[len(sources):]:
            self.outputs.append(outputs[name])

        self.plugin = self.bay.engine(self.desc)
        for i, (mode, data, cell) in enumerate(self.patch):
            match mode:
                case 0 if cell is not None:
                    data[0] = cell.value
                case 1:
                    data = cell.value
                case _:
                    pass
            self.plugin.instance.connect_port(i, data)

    def __del__(self):
        self.plugin.close()

    def step(self, get):
        pulse = self.sources[0]
        if get(pulse):
            for i, (mode, data, cell) in enumerate(self.patch):
                match mode:
                    case 0:
                        if cell is not None:
                            data[0] = cell.value
                    case 1:
                        if data is not cell.value:
                            data[:] = cell.value
                    case 2:
                        pass
            self.plugin.run()
            for i, (mode, data, cell) in enumerate(self.patch):
                match mode:
                    case 2:
                        cell.value = data[0]
                    case _:
                        pass
            return True

class PluginTemplate:
    def __init__(self, model, inputs, py_names, outputs):
        self.model = model
        self.inputs = inputs
        self.outputs = outputs
        self.py_names = py_names
        params = []
        for py_name in py_names:
            params.append(inspect.Parameter(py_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default = None))
        self.sig = inspect.Signature(params)

    def __call__(self, bay, *args, **kwargs):
        arguments = self.sig.bind(*args, **kwargs).arguments
        config = []
        sources = []
        for name, py_name in zip(self.inputs, self.py_names):
            if py_name in arguments:
                config.append(name)
                sources.append(arguments[py_name])
        desc = bay.locator.load(*self.model)
        patch = Patch(bay, desc, config + self.outputs, sources)
        if len(patch.outputs) == 1:
            return patch.outputs[0]
        else:
            return patch.outputs

def midi_to_freq(key, tuning=440.0):
    return 2 ** ((key - 69) / 12.0) * 442.0

On = namedtuple('On', ['note', 'velocity'])
Off = namedtuple('Off', ['note'])

def as_frequency(initial_key, notes, tuning=440.0):
    def _onset_freqs_(m):
        if isinstance(m, On):
            return Some(midi_to_freq(m.note, tuning))
    freqs = Collect(_onset_freqs_, notes)
    return Hold(midi_to_freq(initial_key, tuning), freqs)

def as_velocity(initial, notes):
    def _onset_velocities_(m):
        if isinstance(m, On):
            return Some(m.volume)
    velocities = Collect(_onset_velocities_, notes)
    return Hold(initial, velocities)

def as_gate(initial, notes, func=lambda x: x):
    def _gate_(m):
        if isinstance(m, On):
            return Some(func(1.0))
        if isinstance(m, Off):
            return Some(func(0.0))
    gate = Collect(_gate_, notes)
    return Hold(func(initial), gate)

def as_trig(bay, notes):
    def _trig_(m):
        if isinstance(m, On):
            return Some(None)
    def _hammer_(trig, pulse):
        if len(trig) > 0:
            strike = bay.engine.full(0.0)
            strike[0] = 1.0
            return [strike]
        else:
            return [bay.engine.full(0.0)]
    return Hold(bay.engine.full(0.0), Merge(Collect(_trig_, notes), bay.pulse, _hammer_))
    
class Multiplex:
    def __init__(self, voices):
        self.keys = [69 for voice in range(voices)]
        self.time = [float('-inf') for voice in range(voices)]

    def __call__(self, event, time):
        match event:
            case On(n, v):
                try:
                    i = self.keys.index(n)
                except ValueError:
                    i = min(range(len(self.keys)), key=lambda i: self.time[i])
                    self.keys[i] = n
                self.time[i] = time
                return i, event
            case Off(n):
                try:
                    return self.keys.index(n), event
                except ValueError:
                    return -1, event

def select(i, mux):
    def _this_(k):
        if k[0] == i:
            return Some(k[1])
    return Collect(_this_, mux)

def multiplex(func, now, notes, voices=16):
    mux = Snapshot(Multiplex(voices), notes, now)
    outs = []
    for i in range(voices):
        outs.append(func(select(i, mux)))
    return Compute(lambda *s: sum(s), outs)

def monophonic(bay, tuning=440):
    def _monophonic_(notes, channel_func, *extra):
        gate = as_gate(0.0, notes, bay.engine.full)
        trig = as_trig(bay, notes)
        freq = as_frequency(69, notes, tuning)
        velocity = as_velocity(0.0, notes)
        return channel_func(bay, gate, trig, freq, velocity, *extra)
    return _monophonic_

def polyphonic(bay, now, voices=16, tuning=440):
    def _polyphonic_(notes, channel_func, *extra):
        def _func_(this):
            return monophonic(bay, tuning)(this, channel_func, *extra)
        return multiplex(_func_, now, notes, voices)
    return _polyphonic_

def schedule(t, data, loop=None):
    def _exp_(tu):
        w, u = tu
        if loop:
            t = w % loop
            u = u + (t - w)
        else:
            t = w
        i = bisect.bisect_left(data, t, key=lambda evt: evt[0])
        j = bisect.bisect_right(data, u, key=lambda evt: evt[0])
        yield from [x[1] for x in data[i:j]]
        while loop and loop <= u:
            u -= loop
            j = bisect.bisect_right(data, u, key=lambda evt: evt[0])
            yield from [x[1] for x in data[:j]]
    return Expand(_exp_, Changes(t))

def music(t, tempo, notes, loop=False):
    data = []
    br = 60.0 / tempo
    p = 0.0
    for duration, chord in notes:
        d = br * duration
        for key in chord:
            data.append((p, On(key, 1.0)))
        for key in chord:
            data.append((p + d, Off(key)))
        p += d
    return schedule(t, data, p if loop else None)

lp4pole_faraia = PluginTemplate(
    model = ('lp4pole_1671', b'lp4pole_faraia_oa'),
    inputs = [b'Cutoff Frequency', b'Resonance', b'Input'],
    py_names = ['cutoff', 'resonance', 'input'],
    outputs = [b'Output'])
    
lp4pole_fcrcia = PluginTemplate(
    model = ('lp4pole_1671', b'lp4pole_fcrcia_oa'),
    inputs = [b'Cutoff Frequency', b'Resonance', b'Input'],
    py_names = ['cutoff', 'frequency', 'resonance'],
    outputs = [b'Output'])
    
# _ = PluginTemplate(
#     model = ('mbeq_1197', b'mbeq'),
#     inputs = [b'50Hz gain (low shelving)', b'100Hz gain', b'156Hz gain', b'220Hz gain', b'311Hz gain', b'440Hz gain', b'622Hz gain', b'880Hz gain', b'1250Hz gain', b'1750Hz gain', b'2500Hz gain', b'3500Hz gain', b'5000Hz gain', b'10000Hz gain', b'20000Hz gain', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('svf_1214', b'svf'),
#     inputs = [b'Input', b'Filter type (0=none, 1=LP, 2=HP, 3=BP, 4=BR, 5=AP)', b'Filter freq', b'Filter Q', b'Filter resonance'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('declip_1195', b'declip'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('vocoder_1337', b'vocoder'),
#     inputs = [b'Formant-in', b'Carrier-in', b'Number of bands', b'Left/Right', b'Band 1 Level', b'Band 2 Level', b'Band 3 Level', b'Band 4 Level', b'Band 5 Level', b'Band 6 Level', b'Band 7 Level', b'Band 8 Level', b'Band 9 Level', b'Band 10 Level', b'Band 11 Level', b'Band 12 Level', b'Band 13 Level', b'Band 14 Level', b'Band 15 Level', b'Band 16 Level'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output-out', b'Output2-out'])
#     
# _ = PluginTemplate(
#     model = ('notch_iir_1894', b'notch_iir'),
#     inputs = [b'Center Frequency (Hz)', b'Bandwidth (Hz)', b'Stages(2 poles per stage)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('dahdsr_2021', b'dahdsr_g+t_audio'),
#     inputs = [b'Gate', b'Trigger', b'Delay Time (s)', b'Attack Time (s)', b'Hold Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Envelope Out'])
#     
# _ = PluginTemplate(
#     model = ('dahdsr_2021', b'dahdsr_g+t_control'),
#     inputs = [b'Gate', b'Trigger', b'Delay Time (s)', b'Attack Time (s)', b'Hold Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Envelope Out'])
#     
# _ = PluginTemplate(
#     model = ('dahdsr_2021', b'dahdsr_cg+t_control'),
#     inputs = [b'Gate', b'Trigger', b'Delay Time (s)', b'Attack Time (s)', b'Hold Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Envelope Out'])
#     
# _ = PluginTemplate(
#     model = ('multivoice_chorus_1201', b'multivoiceChorus'),
#     inputs = [b'Number of voices', b'Delay base (ms)', b'Voice separation (ms)', b'Detune (%)', b'LFO frequency (Hz)', b'Output attenuation (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('amp_1654', b'amp_gaia_oa'),
#     inputs = [b'Gain (dB)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('amp_1654', b'amp_gcia_oa'),
#     inputs = [b'Gain (dB)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('analogue_osc_1416', b'analogueOsc'),
#     inputs = [b'Waveform (1=sin, 2=tri, 3=squ, 4=saw)', b'Frequency (Hz)', b'Warmth', b'Instability'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tape_delay_1211', b'tapeDelay'),
#     inputs = [b'Tape speed (inches/sec, 1=normal)', b'Dry level (dB)', b'Tap 1 distance (inches)', b'Tap 1 level (dB)', b'Tap 2 distance (inches)', b'Tap 2 level (dB)', b'Tap 3 distance (inches)', b'Tap 3 level (dB)', b'Tap 4 distance (inches)', b'Tap 4 level (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('matrix_ms_st_1421', b'matrixMSSt'),
#     inputs = [b'Width', b'Mid', b'Side'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Left', b'Right'])
#     
# _ = PluginTemplate(
#     model = ('quantiser50_2028', b'quantiser50'),
#     inputs = [b'Quantise Range Minimum', b'Quantise Range Maximum', b'Match Range', b'Mode (0 = Extend, 1 = Wrap, 2 = Clip)', b'Steps (1 - 50)', b'Value 0', b'Value 1', b'Value 2', b'Value 3', b'Value 4', b'Value 5', b'Value 6', b'Value 7', b'Value 8', b'Value 9', b'Value 10', b'Value 11', b'Value 12', b'Value 13', b'Value 14', b'Value 15', b'Value 16', b'Value 17', b'Value 18', b'Value 19', b'Value 20', b'Value 21', b'Value 22', b'Value 23', b'Value 24', b'Value 25', b'Value 26', b'Value 27', b'Value 28', b'Value 29', b'Value 30', b'Value 31', b'Value 32', b'Value 33', b'Value 34', b'Value 35', b'Value 36', b'Value 37', b'Value 38', b'Value 39', b'Value 40', b'Value 41', b'Value 42', b'Value 43', b'Value 44', b'Value 45', b'Value 46', b'Value 47', b'Value 48', b'Value 49', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Quantised Output', b'Output Changed'])
#     
# _ = PluginTemplate(
#     model = ('sum_1665', b'sum_iaia_oa'),
#     inputs = [b'First Input', b'Second Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Summed Output'])
#     
# _ = PluginTemplate(
#     model = ('sum_1665', b'sum_iaic_oa'),
#     inputs = [b'First Input', b'Second Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Summed Output'])
#     
# _ = PluginTemplate(
#     model = ('sum_1665', b'sum_icic_oc'),
#     inputs = [b'First Input', b'Second Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Summed Output'])
     
sawtooth_fa = PluginTemplate(
    model = ('sawtooth_1641', b'sawtooth_fa_oa'),
    inputs = [b'Frequency'],
    py_names = ['frequency'],
    outputs = [b'Output'])
    
sawtooth_fc = PluginTemplate(
    model = ("sawtooth_1641", b"sawtooth_fc_oa"),
    inputs = [b'Frequency'],
    py_names = ['frequency'],
    outputs = [b'Output'])
 
     
# _ = PluginTemplate(
#     model = ('sin_cos_1881', b'sinCos'),
#     inputs = [b'Base frequency (Hz)', b'Pitch offset'],
#     py_names = ['_', '_'],
#     outputs = [b'Sine output', b'Cosine output'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Noisegate'),
#     inputs = [b'open (dB)', b'attack (ms)', b'close (dB)', b'mains (Hz)', b'in'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Compress'),
#     inputs = [b'measure', b'mode', b'threshold', b'strength', b'attack', b'release', b'gain (dB)', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'state (dB)', b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'CompressX2'),
#     inputs = [b'measure', b'mode', b'threshold', b'strength', b'attack', b'release', b'gain (dB)', b'in.l', b'in.r'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'state (dB)', b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'ToneStack'),
#     inputs = [b'model', b'bass', b'mid', b'treble', b'in'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'AmpVTS'),
#     inputs = [b'over', b'gain', b'bright', b'power', b'tonestack', b'bass', b'mid', b'treble', b'attack', b'squash', b'lowcut', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'CabinetIII'),
#     inputs = [b'model', b'alt', b'gain (dB)', b'in'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'CabinetIV'),
#     inputs = [b'model', b'gain (dB)', b'in'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Plate'),
#     inputs = [b'bandwidth', b'tail', b'damping', b'blend', b'in'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'PlateX2'),
#     inputs = [b'bandwidth', b'tail', b'damping', b'blend', b'in.l', b'in.r'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Saturate'),
#     inputs = [b'mode', b'gain (dB)', b'bias', b'in'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Spice'),
#     inputs = [b'lo.f (Hz)', b'lo.compress', b'lo.gain', b'lo.vol (dB)', b'hi.f (Hz)', b'hi.gain', b'hi.vol (dB)', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'SpiceX2'),
#     inputs = [b'lo.f (Hz)', b'lo.compress', b'lo.gain', b'lo.vol (dB)', b'hi.f (Hz)', b'hi.gain', b'hi.vol (dB)', b'in:l', b'in:r'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out:l', b'out:r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'ChorusI'),
#     inputs = [b't (ms)', b'width (ms)', b'rate (Hz)', b'blend', b'feedforward', b'feedback', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'PhaserII'),
#     inputs = [b'rate', b'lfo', b'depth', b'spread', b'resonance', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'AutoFilter'),
#     inputs = [b'mode', b'filter', b'f (Hz)', b'Q', b'depth', b'lfo/env', b'rate', b'shape', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Scape'),
#     inputs = [b'bpm', b'div', b'Q', b'blend', b'feedback', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Eq10'),
#     inputs = [b'31 Hz', b'63 Hz', b'125 Hz', b'250 Hz', b'500 Hz', b'1 kHz', b'2 kHz', b'4 kHz', b'8 kHz', b'16 kHz', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Eq10X2'),
#     inputs = [b'31 Hz', b'63 Hz', b'125 Hz', b'250 Hz', b'500 Hz', b'1 kHz', b'2 kHz', b'4 kHz', b'8 kHz', b'16 kHz', b'in.l', b'in.r'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Eq4p'),
#     inputs = [b'a.mode', b'a.f (Hz)', b'a.Q', b'a.gain (dB)', b'b.mode', b'b.f (Hz)', b'b.Q', b'b.gain (dB)', b'c.mode', b'c.f (Hz)', b'c.Q', b'c.gain (dB)', b'd.mode', b'd.f (Hz)', b'd.Q', b'd.gain (dB)', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'_latency', b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'EqFA4p'),
#     inputs = [b'a.act', b'a.f (Hz)', b'a.bw', b'a.gain (dB)', b'b.act', b'b.f (Hz)', b'b.bw', b'b.gain (dB)', b'c.act', b'c.f (Hz)', b'c.bw', b'c.gain (dB)', b'd.act', b'd.f (Hz)', b'd.bw', b'd.gain (dB)', b'gain', b'in'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'_latency', b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Wider'),
#     inputs = [b'pan', b'width', b'in'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Narrower'),
#     inputs = [b'mode', b'strength', b'in.l', b'in.r'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'out.l', b'out.r'])
     
sin_fc_ac = PluginTemplate(
    model = ("caps", b"Sin"),
    inputs = [b'f (Hz)', b'volume'],
    py_names = ['frequency', 'volume'],
    outputs = [b'out'])
     
# _ = PluginTemplate(
#     model = ('caps', b'White'),
#     inputs = [b'volume'],
#     py_names = ['_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Fractal'),
#     inputs = [b'rate', b'mode', b'x', b'y', b'z', b'hp', b'volume'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'Click'),
#     inputs = [b'model', b'bpm', b'div', b'vol', b'tone'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('caps', b'CEO'),
#     inputs = [b'ppm', b'volume', b'damping'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'out'])
#     
# _ = PluginTemplate(
#     model = ('decay_1886', b'decay'),
#     inputs = [b'Input', b'Decay Time (s)'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('gsm_1215', b'gsm'),
#     inputs = [b'Dry/wet mix', b'Number of passes', b'Error rate (bits/block)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('foverdrive_1196', b'foverdrive'),
#     inputs = [b'Drive level', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('butterworth_1902', b'bwxover_iir'),
#     inputs = [b'Cutoff Frequency (Hz)', b'Resonance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'LP-Output', b'HP-Output'])
#     
# _ = PluginTemplate(
#     model = ('butterworth_1902', b'buttlow_iir'),
#     inputs = [b'Cutoff Frequency (Hz)', b'Resonance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('butterworth_1902', b'butthigh_iir'),
#     inputs = [b'Cutoff Frequency (Hz)', b'Resonance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('gate_1410', b'gate'),
#     inputs = [b'LF key filter (Hz)', b'HF key filter (Hz)', b'Threshold (dB)', b'Attack (ms)', b'Hold (ms)', b'Decay (ms)', b'Range (dB)', b'Output select (-1 = key listen, 0 = gate, 1 = bypass)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('vynil_1905', b'vynil'),
#     inputs = [b'Year', b'RPM', b'Surface warping', b'Crackle', b'Wear', b'Input L', b'Input R'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output L', b'Output R'])
#     
# _ = PluginTemplate(
#     model = ('quantiser20_2027', b'quantiser20'),
#     inputs = [b'Quantise Range Minimum', b'Quantise Range Maximum', b'Match Range', b'Mode (0 = Extend, 1 = Wrap, 2 = Clip)', b'Steps (1 - 20)', b'Value 0', b'Value 1', b'Value 2', b'Value 3', b'Value 4', b'Value 5', b'Value 6', b'Value 7', b'Value 8', b'Value 9', b'Value 10', b'Value 11', b'Value 12', b'Value 13', b'Value 14', b'Value 15', b'Value 16', b'Value 17', b'Value 18', b'Value 19', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Quantised Output', b'Output Changed'])
#     
# _ = PluginTemplate(
#     model = ('dyson_compress_1403', b'dysonCompress'),
#     inputs = [b'Peak limit (dB)', b'Release time (s)', b'Fast compression ratio', b'Compression ratio', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('dc_remove_1207', b'dcRemove'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('retro_flange_1208', b'retroFlange'),
#     inputs = [b'Average stall (ms)', b'Flange frequency (Hz)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('triple_para_1204', b'triplePara'),
#     inputs = [b'Low-shelving gain (dB)', b'Low-shelving frequency (Hz)', b'Low-shelving slope', b'Band 1 gain (dB)', b'Band 1 frequency (Hz)', b'Band 1 bandwidth (octaves)', b'Band 2 gain (dB)', b'Band 2 frequency (Hz)', b'Band 2 bandwidth (octaves)', b'Band 3 gain (dB)', b'Band 3 frequency (Hz)', b'Band 3 bandwidth (octaves)', b'High-shelving gain (dB)', b'High-shelving frequency (Hz)', b'High-shelving slope', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sync_pulse_2023', b'syncpulse_fapaga_oa'),
#     inputs = [b'Frequency', b'Pulse Width', b'Gate'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sync_pulse_2023', b'syncpulse_fcpcga_oa'),
#     inputs = [b'Frequency', b'Pulse Width', b'Gate'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('rate_shifter_1417', b'rateShifter'),
#     inputs = [b'Rate', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('diode_1185', b'diode'),
#     inputs = [b'Mode (0 for none, 1 for half wave, 2 for full wave)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sync_square_1678', b'syncsquare_faga_oa'),
#     inputs = [b'Frequency', b'Gate'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sync_square_1678', b'syncsquare_fcga_oa'),
#     inputs = [b'Frequency', b'Gate'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
 
adsr = PluginTemplate(
    model = ("adsr_1680", b"adsr_g+t"),
    inputs = [b'Gate', b'Trigger', b'Attack Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
    py_names = ['gate', 'trigger', 'attack', 'decay', 'sustain', 'release'],
    outputs = [b'Envelope Out'])
    
# _ = PluginTemplate(
#     model = ('latency_1914', b'artificialLatency'),
#     inputs = [b'Delay (ms)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('hermes_filter_1200', b'hermesFilter'),
#     inputs = [b'LFO1 freq (Hz)', b'LFO1 wave (0 = sin, 1 = tri, 2 = saw, 3 = squ, 4 = s&h)', b'LFO2 freq (Hz)', b'LFO2 wave (0 = sin, 1 = tri, 2 = saw, 3 = squ, 4 = s&h)', b'Osc1 freq (Hz)', b'Osc1 wave (0 = sin, 1 = tri, 2 = saw, 3 = squ, 4 = noise)', b'Osc2 freq (Hz)', b'Osc2 wave (0 = sin, 1 = tri, 2 = saw, 3 = squ, 4 = noise)', b'Ringmod 1 depth (0=none, 1=AM, 2=RM)', b'Ringmod 2 depth (0=none, 1=AM, 2=RM)', b'Ringmod 3 depth (0=none, 1=AM, 2=RM)', b'Osc1 gain (dB)', b'RM1 gain (dB)', b'Osc2 gain (dB)', b'RM2 gain (dB)', b'Input gain (dB)', b'RM3 gain (dB)', b'Xover lower freq', b'Xover upper freq', b'Dist1 drive', b'Dist2 drive', b'Dist3 drive', b'Filt1 type (0=none, 1=LP, 2=HP, 3=BP, 4=BR, 5=AP)', b'Filt1 freq', b'Filt1 q', b'Filt1 resonance', b'Filt1 LFO1 level', b'Filt1 LFO2 level', b'Filt2 type (0=none, 1=LP, 2=HP, 3=BP, 4=BR, 5=AP)', b'Filt2 freq', b'Filt2 q', b'Filt2 resonance', b'Filt2 LFO1 level', b'Filt2 LFO2 level', b'Filt3 type (0=none, 1=LP, 2=HP, 3=BP, 4=BR, 5=AP)', b'Filt3 freq', b'Filt3 q', b'Filt3 resonance', b'Filt3 LFO1 level', b'Filt3 LFO2 level', b'Delay1 length (s)', b'Delay1 feedback', b'Delay1 wetness', b'Delay2 length (s)', b'Delay2 feedback', b'Delay2 wetness', b'Delay3 length (s)', b'Delay3 feedback', b'Delay3 wetness', b'Band 1 gain (dB)', b'Band 2 gain (dB)', b'Band 3 gain (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('transient_1206', b'transient'),
#     inputs = [b'Attack speed', b'Sustain time', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tracker_2025', b'tracker_gaaadaia_oa'),
#     inputs = [b'Gate', b'Attack Rate (Hz) when Gate High', b'Decay Rate (Hz) when Gate High', b'Attack Rate (Hz) when Gate Low', b'Decay Rate (Hz) when Gate Low', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tracker_2025', b'tracker_gaacdcia_oa'),
#     inputs = [b'Gate', b'Attack Rate (Hz) when Gate High', b'Decay Rate (Hz) when Gate High', b'Attack Rate (Hz) when Gate Low', b'Decay Rate (Hz) when Gate Low', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sequencer32_1676', b'sequencer32'),
#     inputs = [b'Gate (Open > 0)', b'Step Trigger', b'Loop Steps (1 - 32)', b'Reset to Value on Gate Close?', b'Closed Gate Value', b'Value Step 0', b'Value Step 1', b'Value Step 2', b'Value Step 3', b'Value Step 4', b'Value Step 5', b'Value Step 6', b'Value Step 7', b'Value Step 8', b'Value Step 9', b'Value Step 10', b'Value Step 11', b'Value Step 12', b'Value Step 13', b'Value Step 14', b'Value Step 15', b'Value Step 16', b'Value Step 17', b'Value Step 18', b'Value Step 19', b'Value Step 20', b'Value Step 21', b'Value Step 22', b'Value Step 23', b'Value Step 24', b'Value Step 25', b'Value Step 26', b'Value Step 27', b'Value Step 28', b'Value Step 29', b'Value Step 30', b'Value Step 31'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Value Out'])
#     
# _ = PluginTemplate(
#     model = ('revdelay_1605', b'revdelay'),
#     inputs = [b'Input', b'Delay Time (s)', b'Dry Level (dB)', b'Wet Level (dB)', b'Feedback', b'Crossfade samples'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('ringmod_1188', b'ringmod_2i1o'),
#     inputs = [b'Modulation depth (0=none, 1=AM, 2=RM)', b'Input', b'Modulator'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('ringmod_1188', b'ringmod_1i1o1l'),
#     inputs = [b'Modulation depth (0=none, 1=AM, 2=RM)', b'Frequency (Hz)', b'Sine level', b'Triangle level', b'Sawtooth level', b'Square level', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sc2_1426', b'sc2'),
#     inputs = [b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Makeup gain (dB)', b'Sidechain', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('plate_1423', b'plate'),
#     inputs = [b'Reverb time', b'Damping', b'Dry/wet mix', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Left output', b'Right output'])
#     
# _ = PluginTemplate(
#     model = ('single_para_1203', b'singlePara'),
#     inputs = [b'Gain (dB)', b'Frequency (Hz)', b'Bandwidth (octaves)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('square_1643', b'square_fa_oa'),
#     inputs = [b'Frequency'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('square_1643', b'square_fc_oa'),
#     inputs = [b'Frequency'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('crossover_dist_1404', b'crossoverDist'),
#     inputs = [b'Crossover amplitude', b'Smoothing', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('valve_1209', b'valve'),
#     inputs = [b'Distortion level', b'Distortion character', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('comb_1887', b'comb_n'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('comb_1887', b'comb_l'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('comb_1887', b'comb_c'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('wave_terrain_1412', b'waveTerrain'),
#     inputs = [b'x', b'y'],
#     py_names = ['_', '_'],
#     outputs = [b'z'])
#     
# _ = PluginTemplate(
#     model = ('gverb_1216', b'gverb'),
#     inputs = [b'Roomsize (m)', b'Reverb time (s)', b'Damping', b'Input bandwidth', b'Dry signal level (dB)', b'Early reflection level (dB)', b'Tail level (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Left output', b'Right output'])
#     
# _ = PluginTemplate(
#     model = ('bode_shifter_cv_1432', b'bodeShifterCV'),
#     inputs = [b'Base shift', b'Mix (-1=down, +1=up)', b'Input', b'CV Attenuation', b'Shift CV'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Down out', b'Up out', b'Mix out', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('pitch_scale_1194', b'pitchScaleHQ'),
#     inputs = [b'Pitch co-efficient', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('chebstortion_1430', b'chebstortion'),
#     inputs = [b'Distortion', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('decimator_1202', b'decimator'),
#     inputs = [b'Bit depth', b'Sample rate (Hz)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('se4_1883', b'se4'),
#     inputs = [b'RMS/peak', b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Attenuation (dB)', b'Left input', b'Right input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Amplitude (dB)', b'Gain expansion (dB)', b'Left output', b'Right output'])
#     
# _ = PluginTemplate(
#     model = ('shaper_1187', b'shaper'),
#     inputs = [b'Waveshape', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('alias_1407', b'alias'),
#     inputs = [b'Aliasing level', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pulse_1645', b'pulse_fapa_oa'),
#     inputs = [b'Frequency', b'Pulse Width'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pulse_1645', b'pulse_fapc_oa'),
#     inputs = [b'Frequency', b'Pulse Width'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pulse_1645', b'pulse_fcpa_oa'),
#     inputs = [b'Frequency', b'Pulse Width'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pulse_1645', b'pulse_fcpc_oa'),
#     inputs = [b'Frequency', b'Pulse Width'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('giant_flange_1437', b'giantFlange'),
#     inputs = [b'Double delay', b'LFO frequency 1 (Hz)', b'Delay 1 range (s)', b'LFO frequency 2 (Hz)', b'Delay 2 range (s)', b'Feedback', b'Dry/Wet level', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('smooth_decimate_1414', b'smoothDecimate'),
#     inputs = [b'Resample rate', b'Smoothing', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('highpass_iir_1890', b'highpass_iir'),
#     inputs = [b'Cutoff Frequency', b'Stages(2 poles per stage)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('lowpass_iir_1891', b'lowpass_iir'),
#     inputs = [b'Cutoff Frequency', b'Stages(2 poles per stage)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('ratio_2034', b'ratio_nada_oa'),
#     inputs = [b'Numerator', b'Denominator'],
#     py_names = ['_', '_'],
#     outputs = [b'Ratio Output'])
#     
# _ = PluginTemplate(
#     model = ('ratio_2034', b'ratio_nadc_oa'),
#     inputs = [b'Numerator', b'Denominator'],
#     py_names = ['_', '_'],
#     outputs = [b'Ratio Output'])
#     
# _ = PluginTemplate(
#     model = ('ratio_2034', b'ratio_ncda_oa'),
#     inputs = [b'Numerator', b'Denominator'],
#     py_names = ['_', '_'],
#     outputs = [b'Ratio Output'])
#     
# _ = PluginTemplate(
#     model = ('ratio_2034', b'ratio_ncdc_oc'),
#     inputs = [b'Numerator', b'Denominator'],
#     py_names = ['_', '_'],
#     outputs = [b'Ratio Output'])
#     
# _ = PluginTemplate(
#     model = ('valve_rect_1405', b'valveRect'),
#     inputs = [b'Sag level', b'Distortion', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('interpolator_1660', b'interpolator'),
#     inputs = [b'Control Input'],
#     py_names = ['_'],
#     outputs = [b'Interpolated Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'bf2cube'),
#     inputs = [b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output (Base Front Left)', b'Output (Base Front Right)', b'Output (Base Back Left)', b'Output (Base Back Right)', b'Output (Top Front Left)', b'Output (Top Front Right)', b'Output (Top Back Left)', b'Output (Top Back Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'bf2quad'),
#     inputs = [b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output (Front Left)', b'Output (Front Right)', b'Output (Back Left)', b'Output (Back Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'bf2stereo'),
#     inputs = [b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output (Left)', b'Output (Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fmh2oct'),
#     inputs = [b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)', b'Input (R)', b'Input (S)', b'Input (T)', b'Input (U)', b'Input (V)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output (Front Front Left)', b'Output (Front Front Right)', b'Output (Front Right Right)', b'Output (Back Right Right)', b'Output (Back Back Right)', b'Output (Back Back Left)', b'Output (Back Left Left)', b'Output (Front Left Left)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'encode_bformat'),
#     inputs = [b'Input', b'Sound Source X Coordinate', b'Sound Source Y Coordinate', b'Sound Source Z Coordinate'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output (W)', b'Output (X)', b'Output (Y)', b'Output (Z)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'encode_fmh'),
#     inputs = [b'Input', b'Sound Source X Coordinate', b'Sound Source Y Coordinate', b'Sound Source Z Coordinate'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output (W)', b'Output (X)', b'Output (Y)', b'Output (Z)', b'Output (R)', b'Output (S)', b'Output (T)', b'Output (U)', b'Output (V)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'bf_rotate_z'),
#     inputs = [b'Angle of Rotation (Degrees Anticlockwise)', b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output (W)', b'Output (X)', b'Output (Y)', b'Output (Z)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fmh_rotate_z'),
#     inputs = [b'Angle of Rotation (Degrees Anticlockwise)', b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)', b'Input (R)', b'Input (S)', b'Input (T)', b'Input (U)', b'Input (V)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output (W)', b'Output (X)', b'Output (Y)', b'Output (Z)', b'Output (R)', b'Output (S)', b'Output (T)', b'Output (U)', b'Output (V)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'amp_mono'),
#     inputs = [b'Gain', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'amp_stereo'),
#     inputs = [b'Gain', b'Input (Left)', b'Input (Right)'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output (Left)', b'Output (Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'am'),
#     inputs = [b'Input 1', b'Input 2'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'analogue'),
#     inputs = [b'Gate', b'Velocity', b'Frequency (Hz)', b'DCO1 Octave', b'DCO1 Waveform', b'DCO1 LFO Frequency Modulation', b'DCO1 LFO Pulse Width Modulation', b'DCO1 Attack', b'DCO1 Decay', b'DCO1 Sustain', b'DCO1 Release', b'DCO2 Octave', b'DCO2 Waveform', b'DCO2 LFO Frequency Modulation', b'DCO2 LFO Pulse Width Modulation', b'DCO2 Attack', b'DCO2 Decay', b'DCO2 Sustain', b'DCO2 Release', b'LFO Frequency (Hz)', b'LFO Fadein', b'Filter Envelope Modulation', b'Filter LFO Modulation', b'Filter Resonance', b'Filter Attack', b'Filter Decay', b'Filter Sustain', b'Filter Release'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Out'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'canyon_delay'),
#     inputs = [b'In (Left)', b'In (Right)', b'Left to Right Time (Seconds)', b'Left to Right Feedback (Percent)', b'Right to Left Time (Seconds)', b'Right to Left Feedback (Percent)', b'Low-Pass Cutoff (Hz)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Out (Left)', b'Out (Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'disintegrator'),
#     inputs = [b'Probability', b'Multiplier', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'sledgehammer'),
#     inputs = [b'Rate', b'Modulator influence', b'Carrier influence', b'Modulator', b'Carrier'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'delay_0,01s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'delay_0,1s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'delay_1s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'delay_5s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'delay_60s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'track_max_peak'),
#     inputs = [b'Input', b'Envelope Forgetting Factor (s/60dB)'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'track_max_rms'),
#     inputs = [b'Input', b'Envelope Forgetting Factor (s/60dB)'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'track_peak'),
#     inputs = [b'Input', b'Smoothing Factor'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'track_rms'),
#     inputs = [b'Input', b'Smoothing Factor'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fmh2bf'),
#     inputs = [b'Input (W)', b'Input (X)', b'Input (Y)', b'Input (Z)', b'Input (R)', b'Input (S)', b'Input (T)', b'Input (U)', b'Input (V)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output (W)', b'Output (X)', b'Output (Y)', b'Output (Z)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fbdelay_0,01s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input', b'Feedback'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fbdelay_0,1s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input', b'Feedback'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fbdelay_1s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input', b'Feedback'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fbdelay_5s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input', b'Feedback'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'fbdelay_60s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input', b'Feedback'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'freeverb3'),
#     inputs = [b'Input (Left)', b'Input (Right)', b'Freeze Mode', b'Room Size', b'Damping', b'Wet Level', b'Dry Level', b'Width'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output (Left)', b'Output (Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'grain_scatter'),
#     inputs = [b'Input', b'Density (Grains/s)', b'Scatter (s)', b'Grain Length (s)', b'Grain Attack (s)'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'hard_gate'),
#     inputs = [b'Threshold', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'hpf'),
#     inputs = [b'Cutoff Frequency (Hz)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'identity_audio'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'identity_control'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'lofi'),
#     inputs = [b'In (Left)', b'In (Right)', b'Crackling (%)', b'Powersupply Overloading (%)', b'Opamp Bandwidth Limiting (Hz)'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Out (Left)', b'Out (Right)'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'logistic'),
#     inputs = [b'"r" parameter', b'Step frequency'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'lpf'),
#     inputs = [b'Cutoff Frequency (Hz)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'mixer'),
#     inputs = [b'Input 1', b'Input 2'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'noise_source_white'),
#     inputs = [b'Amplitude'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'null_ai'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'null_ao'),
#     inputs = [],
#     py_names = [],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'null_ci'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'null_co'),
#     inputs = [],
#     py_names = [],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'organ'),
#     inputs = [b'Gate', b'Velocity', b'Frequency (Hz)', b'Brass', b'Reed', b'Flute', b'16th Harmonic', b'8th Harmonic', b'5 1/3rd Harmonic', b'4th Harmonic', b'2 2/3rd Harmonic', b'2nd Harmonic', b'Attack Lo (Secs)', b'Decay Lo (Secs)', b'Sustain Lo (Level)', b'Release Lo (Secs)', b'Attack Hi (Secs)', b'Decay Hi (Secs)', b'Sustain Hi (Level)', b'Release Hi (Secs)'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Out'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'peak'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Peak'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'phasemod'),
#     inputs = [b'Gate', b'Velocity', b'Frequency (Hz)', b'DCO1 Modulation', b'DCO1 Octave', b'DCO1 Waveform', b'DCO1 Attack', b'DCO1 Decay', b'DCO1 Sustain', b'DCO1 Release', b'DCO2 Modulation', b'DCO2 Octave', b'DCO2 Waveform', b'DCO2 Attack', b'DCO2 Decay', b'DCO2 Sustain', b'DCO2 Release', b'DCO3 Modulation', b'DCO3 Octave', b'DCO3 Waveform', b'DCO3 Attack', b'DCO3 Decay', b'DCO3 Sustain', b'DCO3 Release', b'DCO4 Modulation', b'DCO4 Octave', b'DCO4 Waveform', b'DCO4 Attack', b'DCO4 Decay', b'DCO4 Sustain', b'DCO4 Release', b'DCO5 Modulation', b'DCO5 Octave', b'DCO5 Waveform', b'DCO5 Attack', b'DCO5 Decay', b'DCO5 Sustain', b'DCO5 Release', b'DCO6 Modulation', b'DCO6 Octave', b'DCO6 Waveform', b'DCO6 Attack', b'DCO6 Decay', b'DCO6 Sustain', b'DCO6 Release'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Out'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'pink_interpolated_audio'),
#     inputs = [b'Highest frequency'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'pink_full_frequency'),
#     inputs = [],
#     py_names = [],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'pink_sh'),
#     inputs = [b'Sample and hold frequency'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'compress_peak'),
#     inputs = [b'Threshold', b'Compression Ratio', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'compress_rms'),
#     inputs = [b'Threshold', b'Compression Ratio', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'expand_peak'),
#     inputs = [b'Threshold', b'Expansion Ratio', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'expand_rms'),
#     inputs = [b'Threshold', b'Expansion Ratio', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'limit_peak'),
#     inputs = [b'Threshold', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'limit_rms'),
#     inputs = [b'Threshold', b'Output Envelope Attack (s)', b'Output Envelope Decay (s)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'sine_faaa'),
#     inputs = [b'Frequency', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'sine_faac'),
#     inputs = [b'Frequency', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'sine_fcaa'),
#     inputs = [b'Frequency', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'sine_fcac'),
#     inputs = [b'Frequency', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'syndrum'),
#     inputs = [b'Trigger', b'Velocity', b'Frequency (Hz)', b'Resonance', b'Frequency Ratio'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Out'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'vcf303'),
#     inputs = [b'In', b'Trigger', b'Cutoff', b'Resonance', b'Envelope Modulation', b'Decay'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Out'])
#     
# _ = PluginTemplate(
#     model = ('cmt', b'wshape_sine'),
#     inputs = [b'Limiting Amplitude', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('inv_1429', b'inv'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('dj_flanger_1438', b'djFlanger'),
#     inputs = [b'LFO sync', b'LFO period (s)', b'LFO depth (ms)', b'Feedback (%)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('delay_1898', b'delay_n'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('delay_1898', b'delay_l'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('delay_1898', b'delay_c'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('foldover_1213', b'foldover'),
#     inputs = [b'Drive', b'Skew', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('gong_beater_1439', b'gongBeater'),
#     inputs = [b'Impulse gain (dB)', b'Strike gain (dB)', b'Strike duration (s)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('karaoke_1409', b'karaoke'),
#     inputs = [b'Vocal volume (dB)', b'Left in', b'Right in'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Left out', b'Right out'])
#     
# _ = PluginTemplate(
#     model = ('gong_1424', b'gong'),
#     inputs = [b'Inner damping', b'Outer damping', b'Mic position', b'Inner size 1', b'Inner stiffness 1 +', b'Inner stiffness 1 -', b'Inner size 2', b'Inner stiffness 2 +', b'Inner stiffness 2 -', b'Inner size 3', b'Inner stiffness 3 +', b'Inner stiffness 3 -', b'Inner size 4', b'Inner stiffness 4 +', b'Inner stiffness 4 -', b'Outer size 1', b'Outer stiffness 1 +', b'Outer stiffness 1 -', b'Outer size 2', b'Outer stiffness 2 +', b'Outer stiffness 2 -', b'Outer size 3', b'Outer stiffness 3 +', b'Outer stiffness 3 -', b'Outer size 4', b'Outer stiffness 4 +', b'Outer stiffness 4 -', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('fad_delay_1192', b'fadDelay'),
#     inputs = [b'Delay (seconds)', b'Feedback (dB)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pitch_scale_1193', b'pitchScale'),
#     inputs = [b'Pitch co-efficient', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('fmod_1656', b'fmod_fama_oa'),
#     inputs = [b'Frequency (Hz)', b'Modulation (Octaves)'],
#     py_names = ['_', '_'],
#     outputs = [b'Modulated Frequency (Hz)'])
#     
# _ = PluginTemplate(
#     model = ('fmod_1656', b'fmod_famc_oa'),
#     inputs = [b'Frequency (Hz)', b'Modulation (Octaves)'],
#     py_names = ['_', '_'],
#     outputs = [b'Modulated Frequency (Hz)'])
#     
# _ = PluginTemplate(
#     model = ('fmod_1656', b'fmod_fcma_oa'),
#     inputs = [b'Frequency (Hz)', b'Modulation (Octaves)'],
#     py_names = ['_', '_'],
#     outputs = [b'Modulated Frequency (Hz)'])
#     
# _ = PluginTemplate(
#     model = ('fmod_1656', b'fmod_fcmc_oc'),
#     inputs = [b'Frequency (Hz)', b'Modulation (Octaves)'],
#     py_names = ['_', '_'],
#     outputs = [b'Modulated Frequency (Hz)'])
#     
# _ = PluginTemplate(
#     model = ('imp_1199', b'imp'),
#     inputs = [b'Impulse ID', b'High latency mode', b'Gain (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('freq_tracker_1418', b'freqTracker'),
#     inputs = [b'Tracking speed', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Frequency (Hz)'])
#     
# _ = PluginTemplate(
#     model = ('sc3_1427', b'sc3'),
#     inputs = [b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Makeup gain (dB)', b'Chain balance', b'Sidechain', b'Left input', b'Right input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Left output', b'Right output'])
#     
# _ = PluginTemplate(
#     model = ('fast_lookahead_limiter_1913', b'fastLookaheadLimiter'),
#     inputs = [b'Input gain (dB)', b'Limit (dB)', b'Release time (s)', b'Input 1', b'Input 2'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Attenuation (dB)', b'Output 1', b'Output 2', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('difference_2030', b'difference_iama_oa'),
#     inputs = [b'Input', b'Input to Subtract'],
#     py_names = ['_', '_'],
#     outputs = [b'Difference Output'])
#     
# _ = PluginTemplate(
#     model = ('difference_2030', b'difference_iamc_oa'),
#     inputs = [b'Input', b'Input to Subtract'],
#     py_names = ['_', '_'],
#     outputs = [b'Difference Output'])
#     
# _ = PluginTemplate(
#     model = ('difference_2030', b'difference_icma_oa'),
#     inputs = [b'Input', b'Input to Subtract'],
#     py_names = ['_', '_'],
#     outputs = [b'Difference Output'])
#     
# _ = PluginTemplate(
#     model = ('difference_2030', b'difference_icmc_oc'),
#     inputs = [b'Input', b'Input to Subtract'],
#     py_names = ['_', '_'],
#     outputs = [b'Difference Output'])
#     
# _ = PluginTemplate(
#     model = ('bandpass_iir_1892', b'bandpass_iir'),
#     inputs = [b'Center Frequency (Hz)', b'Bandwidth (Hz)', b'Stages(2 poles per stage)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('zm1_1428', b'zm1'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('lcr_delay_1436', b'lcrDelay'),
#     inputs = [b'L delay (ms)', b'L level', b'C delay (ms)', b'C level', b'R delay (ms)', b'R level', b'Feedback', b'High damp (%)', b'Low damp (%)', b'Spread', b'Dry/Wet level', b'L input', b'R input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'L output', b'R output'])
#     
# _ = PluginTemplate(
#     model = ('sc1_1425', b'sc1'),
#     inputs = [b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Makeup gain (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('mod_delay_1419', b'modDelay'),
#     inputs = [b'Base delay (s)', b'Delay (s)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('harmonic_gen_1220', b'harmonicGen'),
#     inputs = [b'Fundamental magnitude', b'2nd harmonic magnitude', b'3rd harmonic magnitude', b'4th harmonic magnitude', b'5th harmonic magnitude', b'6th harmonic magnitude', b'7th harmonic magnitude', b'8th harmonic magnitude', b'9th harmonic magnitude', b'10th harmonic magnitude', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sequencer16_1677', b'sequencer16'),
#     inputs = [b'Gate (Open > 0)', b'Step Trigger', b'Loop Steps (1 - 16)', b'Reset to Value on Gate Close?', b'Closed Gate Value', b'Value Step 0', b'Value Step 1', b'Value Step 2', b'Value Step 3', b'Value Step 4', b'Value Step 5', b'Value Step 6', b'Value Step 7', b'Value Step 8', b'Value Step 9', b'Value Step 10', b'Value Step 11', b'Value Step 12', b'Value Step 13', b'Value Step 14', b'Value Step 15'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Value Out'])
#     
# _ = PluginTemplate(
#     model = ('dj_eq_1901', b'dj_eq_mono'),
#     inputs = [b'Lo gain (dB)', b'Mid gain (dB)', b'Hi gain (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('dj_eq_1901', b'dj_eq'),
#     inputs = [b'Lo gain (dB)', b'Mid gain (dB)', b'Hi gain (dB)', b'Input L', b'Input R'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output L', b'Output R', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('phasers_1217', b'lfoPhaser'),
#     inputs = [b'LFO rate (Hz)', b'LFO depth', b'Feedback', b'Spread (octaves)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('phasers_1217', b'fourByFourPole'),
#     inputs = [b'Frequency 1', b'Feedback 1', b'Frequency 2', b'Feedback 2', b'Frequency 3', b'Feedback 3', b'Frequency 4', b'Feedback 4', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('phasers_1217', b'autoPhaser'),
#     inputs = [b'Attack time (s)', b'Decay time (s)', b'Modulation depth', b'Feedback', b'Spread (octaves)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('split_1406', b'split'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'Output 1', b'Output 2'])
#     
# _ = PluginTemplate(
#     model = ('surround_encoder_1401', b'surroundEncoder'),
#     inputs = [b'L', b'R', b'C', b'S'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Lt', b'Rt'])
#     
# _ = PluginTemplate(
#     model = ('sc4m_1916', b'sc4m'),
#     inputs = [b'RMS/peak', b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Makeup gain (dB)', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Amplitude (dB)', b'Gain reduction (dB)', b'Output'])
#     
# _ = PluginTemplate(
#     model = ('comb_splitter_1411', b'combSplitter'),
#     inputs = [b'Band separation (Hz)', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output 1', b'Output 2'])
#     
# _ = PluginTemplate(
#     model = ('fm_osc_1415', b'fmOsc'),
#     inputs = [b'Waveform (1=sin, 2=tri, 3=squ, 4=saw)', b'Frequency (Hz)'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('satan_maximiser_1408', b'satanMaximiser'),
#     inputs = [b'Decay time (samples)', b'Knee point (dB)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('am_pitchshift_1433', b'amPitchshift'),
#     inputs = [b'Enabled', b'Pitch shift (Frequency)', b'Pitch shift (Cents)', b'Buffer size', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('hard_limiter_1413', b'hardLimiter'),
#     inputs = [b'dB limit', b'Wet level', b'Residue level', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('pointer_cast_1910', b'pointerCastDistortion'),
#     inputs = [b'Effect cutoff freq (Hz)', b'Dry/wet mix', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sifter_1210', b'sifter'),
#     inputs = [b'Sift size', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('bandpass_a_iir_1893', b'bandpass_a_iir'),
#     inputs = [b'Center Frequency (Hz)', b'Bandwidth (Hz)', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('hilbert_1440', b'hilbert'),
#     inputs = [b'Input'],
#     py_names = ['_'],
#     outputs = [b'0deg output', b'90deg output', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('sinus_wavewrapper_1198', b'sinusWavewrapper'),
#     inputs = [b'Wrap degree', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('allpass_1895', b'allpass_n'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('allpass_1895', b'allpass_l'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('allpass_1895', b'allpass_c'),
#     inputs = [b'Input', b'Max Delay (s)', b'Delay Time (s)', b'Decay Time (s)'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('quantiser100_2029', b'quantiser100'),
#     inputs = [b'Quantise Range Minimum', b'Quantise Range Maximum', b'Match Range', b'Mode (0 = Extend, 1 = Wrap, 2 = Clip)', b'Steps (1 - 100)', b'Value 0', b'Value 1', b'Value 2', b'Value 3', b'Value 4', b'Value 5', b'Value 6', b'Value 7', b'Value 8', b'Value 9', b'Value 10', b'Value 11', b'Value 12', b'Value 13', b'Value 14', b'Value 15', b'Value 16', b'Value 17', b'Value 18', b'Value 19', b'Value 20', b'Value 21', b'Value 22', b'Value 23', b'Value 24', b'Value 25', b'Value 26', b'Value 27', b'Value 28', b'Value 29', b'Value 30', b'Value 31', b'Value 32', b'Value 33', b'Value 34', b'Value 35', b'Value 36', b'Value 37', b'Value 38', b'Value 39', b'Value 40', b'Value 41', b'Value 42', b'Value 43', b'Value 44', b'Value 45', b'Value 46', b'Value 47', b'Value 48', b'Value 49', b'Value 50', b'Value 51', b'Value 52', b'Value 53', b'Value 54', b'Value 55', b'Value 56', b'Value 57', b'Value 58', b'Value 59', b'Value 60', b'Value 61', b'Value 62', b'Value 63', b'Value 64', b'Value 65', b'Value 66', b'Value 67', b'Value 68', b'Value 69', b'Value 70', b'Value 71', b'Value 72', b'Value 73', b'Value 74', b'Value 75', b'Value 76', b'Value 77', b'Value 78', b'Value 79', b'Value 80', b'Value 81', b'Value 82', b'Value 83', b'Value 84', b'Value 85', b'Value 86', b'Value 87', b'Value 88', b'Value 89', b'Value 90', b'Value 91', b'Value 92', b'Value 93', b'Value 94', b'Value 95', b'Value 96', b'Value 97', b'Value 98', b'Value 99', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Quantised Output', b'Output Changed'])
#     
# _ = PluginTemplate(
#     model = ('triangle_1649', b'triangle_fasa_oa'),
#     inputs = [b'Frequency', b'Slope'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('triangle_1649', b'triangle_fasc_oa'),
#     inputs = [b'Frequency', b'Slope'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('triangle_1649', b'triangle_fcsa_oa'),
#     inputs = [b'Frequency', b'Slope'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('triangle_1649', b'triangle_fcsc_oa'),
#     inputs = [b'Frequency', b'Slope'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('flanger_1191', b'flanger'),
#     inputs = [b'Delay base (ms)', b'Max slowdown (ms)', b'LFO frequency (Hz)', b'Feedback', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('comb_1190', b'comb'),
#     inputs = [b'Band separation (Hz)', b'Feedback', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('random_1661', b'random_fasa_oa'),
#     inputs = [b'Frequency (Hz)', b'Wave Smoothness'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('random_1661', b'random_fasc_oa'),
#     inputs = [b'Frequency (Hz)', b'Wave Smoothness'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('random_1661', b'random_fcsa_oa'),
#     inputs = [b'Frequency (Hz)', b'Wave Smoothness'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('random_1661', b'random_fcsc_oa'),
#     inputs = [b'Frequency (Hz)', b'Wave Smoothness'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('matrix_spatialiser_1422', b'matrixSpatialiser'),
#     inputs = [b'Input L', b'Input R', b'Width'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output L', b'Output R'])
#     
# _ = PluginTemplate(
#     model = ('adsr_1653', b'adsr'),
#     inputs = [b'Driving Signal', b'Trigger Threshold', b'Attack Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'Envelope Out'])
#     
# _ = PluginTemplate(
#     model = ('sequencer64_1675', b'sequencer64'),
#     inputs = [b'Gate (Open > 0)', b'Step Trigger', b'Loop Steps (1 - 64)', b'Reset to Value on Gate Close?', b'Closed Gate Value', b'Value Step 0', b'Value Step 1', b'Value Step 2', b'Value Step 3', b'Value Step 4', b'Value Step 5', b'Value Step 6', b'Value Step 7', b'Value Step 8', b'Value Step 9', b'Value Step 10', b'Value Step 11', b'Value Step 12', b'Value Step 13', b'Value Step 14', b'Value Step 15', b'Value Step 16', b'Value Step 17', b'Value Step 18', b'Value Step 19', b'Value Step 20', b'Value Step 21', b'Value Step 22', b'Value Step 23', b'Value Step 24', b'Value Step 25', b'Value Step 26', b'Value Step 27', b'Value Step 28', b'Value Step 29', b'Value Step 30', b'Value Step 31', b'Value Step 32', b'Value Step 33', b'Value Step 34', b'Value Step 35', b'Value Step 36', b'Value Step 37', b'Value Step 38', b'Value Step 39', b'Value Step 40', b'Value Step 41', b'Value Step 42', b'Value Step 43', b'Value Step 44', b'Value Step 45', b'Value Step 46', b'Value Step 47', b'Value Step 48', b'Value Step 49', b'Value Step 50', b'Value Step 51', b'Value Step 52', b'Value Step 53', b'Value Step 54', b'Value Step 55', b'Value Step 56', b'Value Step 57', b'Value Step 58', b'Value Step 59', b'Value Step 60', b'Value Step 61', b'Value Step 62', b'Value Step 63'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Value Out'])
#     
# _ = PluginTemplate(
#     model = ('xfade_1915', b'xfade'),
#     inputs = [b'Crossfade', b'Input A left', b'Input A right', b'Input B left', b'Input B right'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output left', b'Output right'])
#     
# _ = PluginTemplate(
#     model = ('xfade_1915', b'xfade4'),
#     inputs = [b'Crossfade', b'Input A left', b'Input A right', b'Input B left', b'Input B right'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Output A left', b'Output A right', b'Output B left', b'Output B right'])
#     
# _ = PluginTemplate(
#     model = ('step_muxer_1212', b'stepMuxer'),
#     inputs = [b'Crossfade time (in ms)', b'Clock', b'Input 1', b'Input 2', b'Input 3', b'Input 4', b'Input 5', b'Input 6', b'Input 7', b'Input 8'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sc4_1882', b'sc4'),
#     inputs = [b'RMS/peak', b'Attack time (ms)', b'Release time (ms)', b'Threshold level (dB)', b'Ratio (1:n)', b'Knee radius (dB)', b'Makeup gain (dB)', b'Left input', b'Right input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Amplitude (dB)', b'Gain reduction (dB)', b'Left output', b'Right output'])
#     
# _ = PluginTemplate(
#     model = ('bode_shifter_1431', b'bodeShifter'),
#     inputs = [b'Frequency shift', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Down out', b'Up out', b'latency'])
#     
# _ = PluginTemplate(
#     model = ('matrix_st_ms_1420', b'matrixStMS'),
#     inputs = [b'Left', b'Right'],
#     py_names = ['_', '_'],
#     outputs = [b'Mid', b'Side'])
#     
# _ = PluginTemplate(
#     model = ('ls_filter_1908', b'lsFilter'),
#     inputs = [b'Filter type (0=LP, 1=BP, 2=HP)', b'Cutoff frequency (Hz)', b'Resonance', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('impulse_1885', b'impulse_fc'),
#     inputs = [b'Frequency (Hz)'],
#     py_names = ['_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('delayorama_1402', b'delayorama'),
#     inputs = [b'Random seed', b'Input gain (dB)', b'Feedback (%)', b'Number of taps', b'First delay (s)', b'Delay range (s)', b'Delay change', b'Delay random (%)', b'Amplitude change', b'Amplitude random (%)', b'Dry/wet mix', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_reflector', b'tap_reflector'),
#     inputs = [b'Fragment Length [ms]', b'Dry Level [dB]', b'Wet Level [dB]', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_tubewarmth', b'tap_tubewarmth'),
#     inputs = [b'Drive', b'Tape--Tube Blend', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('amp', b'amp_mono'),
#     inputs = [b'Gain', b'Input'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('amp', b'amp_stereo'),
#     inputs = [b'Gain', b'Input (Left)', b'Input (Right)'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output (Left)', b'Output (Right)'])
#     
# _ = PluginTemplate(
#     model = ('tap_pinknoise', b'tap_pinknoise'),
#     inputs = [b'Fractal Dimension', b'Signal Level [dB]', b'Noise Level [dB]', b'Input'],
#     py_names = ['_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_eq', b'tap_equalizer'),
#     inputs = [b'Band 1 Gain [dB]', b'Band 2 Gain [dB]', b'Band 3 Gain [dB]', b'Band 4 Gain [dB]', b'Band 5 Gain [dB]', b'Band 6 Gain [dB]', b'Band 7 Gain [dB]', b'Band 8 Gain [dB]', b'Band 1 Freq [Hz]', b'Band 2 Freq [Hz]', b'Band 3 Freq [Hz]', b'Band 4 Freq [Hz]', b'Band 5 Freq [Hz]', b'Band 6 Freq [Hz]', b'Band 7 Freq [Hz]', b'Band 8 Freq [Hz]', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_limiter', b'tap_limiter'),
#     inputs = [b'Limit Level [dB]', b'Output Volume [dB]', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'latency', b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_vibrato', b'tap_vibrato'),
#     inputs = [b'Frequency [Hz]', b'Depth [%]', b'Dry Level [dB]', b'Wet Level [dB]', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'latency', b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_pitch', b'tap_pitch'),
#     inputs = [b'Semitone Shift', b'Rate Shift [%]', b'Dry Level [dB]', b'Wet Level [dB]', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'latency', b'Output'])
#     
# function = 0  # 2:1 compression starting at -6dB
#            1  # 2:1 compression starting at -9dB
#            2  # 2:1 compression starting at -12dB
#            3  # 2:1 compression starting at -18dB
#            4  # 2.5:1 compression starting at -12dB
#            5  # 3:1 compression starting at -12dB
#            6  # 3:1 compression starting at -15dB
#            7  # Compressor/Gate
#            8  # Expander
#            9  # Hard limiter at -6dB
#            10 # Hard limiter at -12dB
#            11 # Hard noise gate at -35dB
#            12 # Soft limiter
#            13 # Soft knee comp/gate (-24dB threshold)
#            14 # Soft noise gate below -36dB
tap_dynamics_st = PluginTemplate(
    model = ('tap_dynamics_st', b'tap_dynamics_st'),
    inputs = [b'Attack [ms]', b'Release [ms]', b'Offset Gain [dB]', b'Makeup Gain [dB]', b'Stereo Mode', b'Function', b'Input Left', b'Input Right'],
    py_names = ['attack_ms', 'release_ms', 'offset_gain', 'makeup_gain', 'stereo_mode', 'function', 'input_left', 'input_right'],
    outputs = [b'Envelope Volume (L) [dB]', b'Envelope Volume (R) [dB]', b'Gain Adjustment (L) [dB]', b'Gain Adjustment (R) [dB]', b'Output Left', b'Output Right'])
     
# _ = PluginTemplate(
#     model = ('tap_eqbw', b'tap_equalizer_bw'),
#     inputs = [b'Band 1 Gain [dB]', b'Band 2 Gain [dB]', b'Band 3 Gain [dB]', b'Band 4 Gain [dB]', b'Band 5 Gain [dB]', b'Band 6 Gain [dB]', b'Band 7 Gain [dB]', b'Band 8 Gain [dB]', b'Band 1 Freq [Hz]', b'Band 2 Freq [Hz]', b'Band 3 Freq [Hz]', b'Band 4 Freq [Hz]', b'Band 5 Freq [Hz]', b'Band 6 Freq [Hz]', b'Band 7 Freq [Hz]', b'Band 8 Freq [Hz]', b'Band 1 Bandwidth [octaves]', b'Band 2 Bandwidth [octaves]', b'Band 3 Bandwidth [octaves]', b'Band 4 Bandwidth [octaves]', b'Band 5 Bandwidth [octaves]', b'Band 6 Bandwidth [octaves]', b'Band 7 Bandwidth [octaves]', b'Band 8 Bandwidth [octaves]', b'Input'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sine', b'sine_faaa'),
#     inputs = [b'Frequency (Hz)', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sine', b'sine_faac'),
#     inputs = [b'Frequency (Hz)', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sine', b'sine_fcaa'),
#     inputs = [b'Frequency (Hz)', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('sine', b'sine_fcac'),
#     inputs = [b'Frequency (Hz)', b'Amplitude'],
#     py_names = ['_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('delay', b'delay_5s'),
#     inputs = [b'Delay (Seconds)', b'Dry/Wet Balance', b'Input'],
#     py_names = ['_', '_', '_'],
#     outputs = [b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_deesser', b'tap_deesser'),
#     inputs = [b'Threshold Level [dB]', b'Frequency [Hz]', b'Sidechain Filter', b'Monitor', b'Input'],
#     py_names = ['_', '_', '_', '_', '_'],
#     outputs = [b'Attenuation [dB]', b'Output'])
#     
# _ = PluginTemplate(
#     model = ('tap_doubler', b'tap_doubler'),
#     inputs = [b'Time Tracking', b'Pitch Tracking', b'Dry Level [dB]', b'Dry Left Position', b'Dry Right Position', b'Wet Level [dB]', b'Wet Left Position', b'Wet Right Position', b'Input_L', b'Input_R'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output_L', b'Output_R'])
#     
# _ = PluginTemplate(
#     model = ('tap_chorusflanger', b'tap_chorusflanger'),
#     inputs = [b'Frequency [Hz]', b'L/R Phase Shift [deg]', b'Depth [%]', b'Delay [ms]', b'Contour [Hz]', b'Dry Level [dB]', b'Wet Level [dB]', b'Input_L', b'Input_R'],
#     py_names = ['_', '_', '_', '_', '_', '_', '_', '_', '_'],
#     outputs = [b'Output_L', b'Output_R'])
#     
# _ = PluginTemplate(
#     model = ('tap_rotspeak', b'tap_rotspeak'),
#     inputs = [b'Rotor Frequency [Hz]', b'Horn Frequency [Hz]', b'Mic Distance [%]', b'Rotor/Horn Mix', b'Input L', b'Input R'],
#     py_names = ['_', '_', '_', '_', '_', '_'],
#     outputs = [b'latency', b'Output L', b'Output R'])

sigmoid = PluginTemplate(
    model = ('tap_sigmoid', b'tap_sigmoid'),
    inputs = [b'Pre Gain [dB]', b'Post Gain [dB]', b'Input'],
    py_names = ['pre', 'post', 'input'],
    outputs = [b'Output'])

reverb = PluginTemplate(
    model = ('tap_reverb', b'tap_reverb'),
    inputs = [b'Decay [ms]', b'Dry Level [dB]', b'Wet Level [dB]', b'Comb Filters', b'Allpass Filters', b'Bandpass Filter', b'Enhanced Stereo', b'Reverb Type', b'Input Left', b'Input Right'],
    py_names = ['decay_ms', 'dry_level', 'wet_level', 'comb_filters', 'allpass_filters', 'bandpass_filters', 'enchanted_stereo', 'reverb_type', 'left', 'right'],
    outputs = [b'Output Left', b'Output Right'])
     
autopan = PluginTemplate(
    model = ('tap_autopan', b'tap_autopan'),
    inputs = [b'Frequency [Hz]', b'Depth [%]', b'Gain [dB]', b'Input L', b'Input R'],
    py_names = ['frequency', 'depth', 'gain', 'left', 'right'],
    outputs = [b'Output L', b'Output R'])

echo = PluginTemplate(
    model = ('tap_echo', b'tap_stereo_echo'),
    inputs = [b'L Delay [ms]', b'L Feedback [%]', b'R/Haas Delay [ms]', b'R/Haas Feedback [%]', b'L Echo Level [dB]', b'R Echo Level [dB]', b'Dry Level [dB]', b'Cross Mode', b'Haas Effect', b'Swap Outputs', b'Input Left', b'Input Right'],
    py_names = ['l_delay_ms', 'l_feedback_pc', 'r_haas_delay_ms', 'r_haas_feedback_pc', 'l_echo_level', 'r_echo_level', 'dry_level', 'cross_mode', 'haas_effect', 'swap_outputs', 'left', 'right'],
    outputs = [b'Output Left', b'Output Right'])

tremolo = PluginTemplate(
    model = ('tap_tremolo', b'tap_tremolo'),
    inputs = [b'Frequency [Hz]', b'Depth [%]', b'Gain [dB]', b'Input_0'],
    py_names = ['frequency', 'depth_pc', 'gain', 'input'],
    outputs = [b'Output_0'])
    
lpf = PluginTemplate(
    model = ('filter', b'lpf'),
    inputs = [b'Cutoff Frequency (Hz)', b'Input'],
    py_names = ['cutoff', 'input'],
    outputs = [b'Output'])
     
hpf = PluginTemplate(
    model = ('filter', b'hpf'),
    inputs = [b'Cutoff Frequency (Hz)', b'Input'],
    py_names = ['cutoff', 'input'],
    outputs = [b'Output'])

# function = 0  # 2:1 compression starting at -6dB
#            1  # 2:1 compression starting at -9dB
#            2  # 2:1 compression starting at -12dB
#            3  # 2:1 compression starting at -18dB
#            4  # 2.5:1 compression starting at -12dB
#            5  # 3:1 compression starting at -12dB
#            6  # 3:1 compression starting at -15dB
#            7  # Compressor/Gate
#            8  # Expander
#            9  # Hard limiter at -6dB
#            10 # Hard limiter at -12dB
#            11 # Hard noise gate at -35dB
#            12 # Soft limiter
#            13 # Soft knee comp/gate (-24dB threshold)
#            14 # Soft noise gate below -36dB
tap_dynamics_mono = PluginTemplate(
    model = ('tap_dynamics_m', b'tap_dynamics_m'),
    inputs = [b'Attack [ms]', b'Release [ms]', b'Offset Gain [dB]', b'Makeup Gain [dB]', b'Function', b'Input'],
    py_names = ['attack_ms', 'release_ms', 'offset_gain', 'makeup_gain', 'function', 'input'],
    outputs = [b'Envelope Volume [dB]', b'Gain Adjustment [dB]', b'Output'])

noise_white = PluginTemplate(
    model = ('noise', b'noise_white'),
    inputs = [b'Amplitude'],
    py_names = ['amplitude'],
    outputs = [b'Output'])
