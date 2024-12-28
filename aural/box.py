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
                    u = value
                    w = 1.0 - value
                    if hint['logarithmic']:
                        value = math.exp(math.log(lower) * u + math.log(upper) * w)
                    else:
                        value = lower * u + upper * w
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
        self.plugin = None

    def connect(self, dependent):
        super().connect(dependent)
        if len(self.dependents) == 1:
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

    def discard(self, dependent):
        super().discard(dependent)
        if len(self.dependents) == 0:
            self.plugin.close()
            self.plugin = None

    def step(self, enqueue, firing):
        pulse = self.sources[0]
        if pulse in firing:
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
            super().step(enqueue, firing)

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

sin_fc_ac = PluginTemplate(
    model = ("caps", b"Sin"),
    inputs = [b'f (Hz)', b'volume'],
    py_names = ['frequency', 'volume'],
    outputs = [b'out'])

sawtooth_fc = PluginTemplate(
    model = ("sawtooth_1641", b"sawtooth_fc_oa"),
    inputs = [b'Frequency'],
    py_names = ['frequency'],
    outputs = [b'Output'])

adsr = PluginTemplate(
    model = ("adsr_1680", b"adsr_g+t"),
    inputs = [b'Gate', b'Trigger', b'Attack Time (s)', b'Decay Time (s)', b'Sustain Level', b'Release Time (s)'],
    py_names = ['gate', 'trigger', 'attack', 'decay', 'sustain', 'release'],
    outputs = [b'Envelope Out'])

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
