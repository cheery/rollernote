import numpy
import ctypes
import math
import os
from . import capi

def load(name, index):
    lib = capi.load_module(name)
    desc = lib.ladspa_descriptor(index)
    if desc:
        return Descriptor(lib, desc)

def load_all(name):
    lib = capi.load_module(name)
    i = 0
    desc = lib.ladspa_descriptor(0)
    while desc:
        yield Descriptor(lib, desc)
        i += 1
        desc = lib.ladspa_descriptor(i)

class Descriptor:
    def __init__(self, lib, raw):
        self.lib = lib
        self.raw = raw
        rec = raw.contents
        self.info = {
            'uniqueID': rec.UniqueID,
            'label': rec.Label,
            'properties': list(decode_properties(rec.Properties)),
            'copyright': rec.Copyright,
            'ports': list(decode_ports(rec)),
        }

    def __call__(self, sample_rate):
        handle = self.raw.contents.instantiate(self.raw, sample_rate)
        if not bool(handle):
            raise Exception("cannot instantiate")
        return Handle(self, handle)

class Handle:
    def __init__(self, desc, handle):
        self.desc = desc
        self.handle = handle
        self.ports = {}

    def connect_port(self, index, data):
        self.ports[index] = data
        if isinstance(data, numpy.ndarray):
            data = ctypes.cast(data.ctypes, ctypes.POINTER(capi.Data))
        self.desc.raw.contents.connect_port(self.handle, index, data)

    def activate(self):
        if bool(self.desc.raw.contents.activate):
            self.desc.raw.contents.activate(self.handle)

    def run(self, sample_count):
        self.desc.raw.contents.run(self.handle, sample_count)

    def deactivate(self):
        if bool(self.desc.raw.contents.deactivate):
            self.desc.raw.contents.deactivate(self.handle)

    def cleanup(self):
        self.desc.raw.contents.cleanup(self.handle)

    def connect(self, wargs, sample_count, wout=None):
        outs = []
        for i, port in enumerate(self.desc.info['ports']):
            name = port['name']
            kind = port['type']
            if name in wargs:
                data = wargs[name]
            elif kind == 'output':
                data = cell()
                outs.append(data)
            elif kind == 'output*':
                data = numpy.zeros(sample_count, numpy.float32)
                outs.append(data)
            elif kind == 'input' and port['hint']['default'] is not None:
                hint = port['hint']
                logarithmic = hint['logarithmic']
                default = hint['default']
                value = default['value']
                if default['ratio']:
                    u = value
                    w = 1 - u
                    if logarithmic:
                        value = math.exp(math.log(hint['lower']) * u + math.log(hint['upper'] * w))
                    else:
                        value = hint['lower'] * u + hint['upper'] * w
                else:
                    data = cell(value)
            else:
                raise Exception(f"{name} is a required field")
            self.connect_port(i, data)
        if wout is not None:
            names = {}
            for i, port in enumerate(self.desc.info['ports']):
                names[port['name']] = i
            return [self.ports[names[w]] for w in wout]
        return outs

def decode_properties(prop):
    if prop & capi.PROPERTY_REALTIME > 0:
        yield 'realtime'
    if prop & capi.PROPERTY_INPLACE_BROKEN > 0:
        yield 'inplace_broken'
    if prop & capi.PROPERTY_HARD_RT_CAPABLE > 0:
        yield 'hard_rt_capable'
    assert (prop & 0x7) == prop, prop

def decode_ports(rec):
    for i in range(rec.PortCount):
        port = {
            'type': decode_port_type(rec.PortDescriptors[i]),
            'name': rec.PortNames[i],
            'hint': decode_port_hint(rec.PortRangeHints[i]),
        }
        yield port

def decode_port_type(d):
    # Not sure what the 0x10 flag is
    assert d & 0x1F == d, d >> 4
    if d & 0xF == capi.PORT_INPUT | capi.PORT_CONTROL:
        return 'input'
    if d & 0xF == capi.PORT_INPUT | capi.PORT_AUDIO:
        return 'input*'
    if d & 0xF == capi.PORT_OUTPUT | capi.PORT_CONTROL:
        return 'output'
    if d & 0xF == capi.PORT_OUTPUT | capi.PORT_AUDIO:
        return 'output*'

def decode_port_hint(hint):
    d = hint.HintDescriptor
    dr = d & capi.HINT_DEFAULT_MASK
    if dr == capi.HINT_DEFAULT_MINIMUM:
        default = {'value': 0.0, 'ratio': True}
    elif dr == capi.HINT_DEFAULT_LOW:
        default = {'value': 0.25, 'ratio': True}
    elif dr == capi.HINT_DEFAULT_MIDDLE:
        default = {'value': 0.5, 'ratio': True}
    elif dr == capi.HINT_DEFAULT_HIGH:
        default = {'value': 0.75, 'ratio': True}
    elif dr == capi.HINT_DEFAULT_MAXIMUM:
        default = {'value': 1.0, 'ratio': True}
    elif dr == capi.HINT_DEFAULT_0:
        default = {'value': 0.0, 'ratio': False}
    elif dr == capi.HINT_DEFAULT_1:
        default = {'value': 1.0, 'ratio': False}
    elif dr == capi.HINT_DEFAULT_100:
        default = {'value': 100.0, 'ratio': False}
    elif dr == capi.HINT_DEFAULT_440:
        default = {'value': 440.0, 'ratio': False}
    else:
        assert dr == capi.HINT_DEFAULT_NONE, dr
        default = None

    return {
        'toggled': d & capi.HINT_TOGGLED > 0,
        'sample_rate': d & capi.HINT_SAMPLE_RATE > 0,
        'logarithmic': d & capi.HINT_LOGARITHMIC > 0,
        'integer': d & capi.HINT_INTEGER > 0,
        'default': default,
        'lower': hint.LowerBound if d & capi.HINT_BOUNDED_BELOW > 0 else None,
        'upper': hint.UpperBound if d & capi.HINT_BOUNDED_ABOVE > 0 else None,
    }

def cell(value=0.0):
    return (capi.Data*1)(value)

class Locator:
    def __init__(self, paths):
        self.paths = paths
        self.modules = {}
        for path in paths:
            for name in capi.list_modules(path):
                root = os.path.splitext(os.path.basename(name))[0]
                if root not in self.modules:
                    self.modules[root] = name

    def load(self, root, index=0):
        name = self.modules[root]
        if isinstance(index, int):
            this = load(name, index)
        else:
            this = None
            for desc in load_all(name):
                if desc.info['label'] == index:
                    this = desc
                    break
        if this is None:
            contents = []
            for desc in load_all(name):
                contents.append(desc.info['label'])
            raise Exception(f"{index} not in module, contents: {contents}")
        return this

    def list(self):
        for root, name in self.modules.items():
            try:
                for desc in load_all(name):
                    yield root, desc.info['label'], desc
            except AttributeError:
                pass

class Engine:
    def __init__(self, sample_rate, sample_count):
        self.sample_rate = sample_rate
        self.sample_count = sample_count
        self.sample_step = sample_count / sample_rate

    def __call__(self, desc):
        return Plugin(self, desc(self.sample_rate))

    def cell(self, value):
        return cell(value)

    def zeros(self):
        return numpy.zeros(self.sample_count, numpy.float32)

    def full(self, value):
        return numpy.full(self.sample_count, value, numpy.float32)

class Plugin:
    def __init__(self, engine, instance):
        self.engine = engine
        self.instance = instance
        self.instance.activate()

    def close(self):
        self.instance.deactivate()
        self.instance.cleanup()

    def connect(self, wargs, wout=None):
        return self.instance.connect(wargs, self.engine.sample_count, wout)

    def run(self):
        self.instance.run(self.engine.sample_count)
