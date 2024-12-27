import reaction
import math
import inspect

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
                    lower = hint['lower']
                    upper = hint['upper']
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


# class AsFrequency:
#     def __init__(self, clavier, output, tuning):
#         self.clavier = clavier
#         self.output = output
#         self.tuning = tuning
# 
#     def run(self):
#         hz = self.output[0]
#         for evt in self.clavier.events:
#             if evt[1] == 'on':
#                 hz = midi_to_freq(evt[2], self.tuning)
#         self.output[0] = hz
# 
# def as_frequency(clavier, initial_key=69, tuning=440.0):
#     cell = CellPlan(midi_to_freq(initial_key, tuning))
#     @just_deploy
#     def _impl_(locator, engine, mapping):
#         return AsFrequency(clavier, register(cell, engine, mapping), tuning)
#     return cell
# 
# class Channel:
#     def __init__(self, gate, trig, hz, velo, wiring, out):
#         self.gate   = gate
#         self.trig   = trig
#         self.hz     = hz
#         self.velo   = velo
#         self.wiring = wiring
#         self.out    = out
#         self.time = 0.0
#         self.key  = 69
# 
#     def run(self):
#         self.wiring.run()
#         self.trig.fill(-1.0)
# 
# class Polyphonic:
#     def __init__(self, clavier, channels, output):
#         self.clavier = clavier
#         self.channels = channels
#         self.output = output
#         self.active = {}
#         self.i = 0
# 
#     def key_on(self, key, vel=1.0):
#         if key in self.active and self.active[key].key == key:
#             chan = self.active[key]
#         else:
#             chan = min(self.channels, key=lambda chan: chan.time)
#         chan.key = key
#         chan.time = self.i
#         chan.velo[0] = vel
#         chan.hz[0] = midi_to_freq(key)
#         chan.gate.fill(1.0)
#         chan.trig[0] = 1.0
#         self.active[chan.key] = chan
# 
#     def key_off(self, key):
#         chan = self.active[key]
#         if chan.key == key:
#             chan.gate.fill(-1.0)
# 
#     def run(self):
#         for evt in self.clavier.events:
#             if evt[1] == 'on':
#                 self.key_on(*evt[2:])
#             if evt[1] == 'off':
#                 self.key_off(*evt[2:])
#         self.i += 1
#         self.output.fill(0.0)
#         for chan in self.channels:
#             chan.run()
#             self.output += chan.out
# 
# def polyphonic(voices=16):
#     def _polyphonic_(clavier, channel):
#         wout = BufferPlan()
#         @just_deploy
#         def _impl_(locator, engine, mapping):
#             that = Template()
#             gate = BufferPlan(-1.0)
#             trig = BufferPlan(-1.0)
#             hz   = CellPlan(440.0)
#             velo = CellPlan(1.0)
#             out  = wrap(that, channel, gate, trig, hz, velo)
#             out  = wrap(that, stratify, out)
#             channels = []
#             for i in range(voices):
#                 mapping_ = {}
#                 g = register(gate, engine, mapping_)
#                 t = register(trig, engine, mapping_)
#                 h = register(hz,   engine, mapping_)
#                 v = register(velo, engine, mapping_)
#                 ut = register(out, engine, mapping_)
#                 wiring = that.wire(locator, engine, mapping_)
#                 chan = Channel(g,t,h,v,wiring,ut)
#                 channels.append(chan)
#             return Polyphonic(clavier, channels, register(wout, engine, mapping))
#         return wout
#     return _polyphonic_
# 
# class Clavier:
#     def __init__(self):
#         self.incoming = []
#         self.events = []
# 
#     def run(self):
#         self.events = self.incoming
#         self.incoming = []
# 
#     def key_on(self, key, velocity=1.0):
#         self.incoming.append((0.0, 'on', key, velocity))
# 
#     def key_off(self, key):
#         self.incoming.append((0.0, 'off', key))
# 
# class Song:
#     def __init__(self, engine, song, loop=None):
#         self.engine = engine
#         self.song = song
#         self.loop = loop
#         self.time = 0.0
#         self.events = []
# 
#     def run(self):
#         ntime = self.time + self.engine.sample_step
#         i = bisect.bisect_left(self.song, self.time, key=lambda evt: evt[0])
#         j = bisect.bisect_right(self.song, ntime, key=lambda evt: evt[0])
#         self.events = self.song[i:j]
#         while self.loop and self.loop <= ntime:
#             ntime -= self.loop
#             j = bisect.bisect_right(self.song, ntime, key=lambda evt: evt[0])
#             self.events += self.song[:j]
#         self.time = ntime
