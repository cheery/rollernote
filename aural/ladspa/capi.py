import ctypes
import os
from ctypes import Structure, POINTER, CFUNCTYPE

version = "1.1"
version_major = 1
version_minor = 1

# LADSPA plugins distinguish between control and audio data.
# Ports are inputs or outputs for audio or control data
# Each plugin is 'run' for a 'block' corresponding to a short time interval measured in samples.
# Audio data is arrays of LADSPA_Data
# Control data is single LADSPA_Data values
# Control data has a single value at the start of a call to the 'run' or 'run_adding',
# All input/output ports have been connected to relevant data location before asked to run.

# Fundamental data type passed in and out of plugin.
# For audio, 1.0f is the 0dB reference amplitude.
Data = ctypes.c_float

# Special plugin properties flags are passed in as Properties type.
Properties = ctypes.c_int

PROPERTY_REALTIME = 0x1 # Has a real-time dependency (output must not be cached or subject to latency)
PROPERTY_INPLACE_BROKEN = 0x2 # Indicates that the plugin may cease to work if host uses same data for input and output
PROPERTY_HARD_RT_CAPABLE = 0x4 # Indicates the plugin is capable of running in hard real-time environment.

# Note that port can't be both input/output, or control/audio
PortDescriptor = ctypes.c_int
PORT_INPUT = 0x1
PORT_OUTPUT = 0x2
PORT_CONTROL = 0x4
PORT_AUDIO = 0x8

# Plugin port range hints
PortRangeHintDescriptor = ctypes.c_int

HINT_BOUNDED_BELOW = 0x1 # Bounded below is set (inclusive)
HINT_BOUNDED_ABOVE = 0x2 # Bounded above is set (inclusive)
HINT_TOGGLED = 0x4       # Should be considered boolean toggle
HINT_SAMPLE_RATE = 0x8   # If set, indicates bounds specified should be interpreted as multiples of the sample rate.
HINT_LOGARITHMIC = 0x10  # Useful to view values with logarithmic scale.
HINT_INTEGER = 0x20      # Only integer values, and bounds should be widened by 0.1 to avoid rounding errors.

HINT_DEFAULT_MASK = 0x3C0
HINT_DEFAULT_NONE = 0x0
HINT_DEFAULT_MINIMUM = 0x40 # Suggested lower bound should be used as default.
HINT_DEFAULT_LOW = 0x80     # LOG: exp(log(lower) * 0.75 + log(upper) * 0.25)
                            # LIN: lower * 0.75 + upper * 0.25
HINT_DEFAULT_MIDDLE = 0xC0
HINT_DEFAULT_HIGH = 0x100
HINT_DEFAULT_MAXIMUM = 0x140
HINT_DEFAULT_0 = 0x200
HINT_DEFAULT_1 = 0x240
HINT_DEFAULT_100 = 0x280
HINT_DEFAULT_440 = 0x2C0 # Or 442

class PortRangeHint(Structure):
    _fields_ = [
      ('HintDescriptor', PortRangeHintDescriptor),
      ('LowerBound', Data),
      ('UpperBound', Data),
    ]

# Do not attempt to interpret.
Handle = ctypes.c_void_p

class Descriptor(Structure):
    pass

Descriptor._fields_ = [
      ('UniqueID', ctypes.c_ulong), # Indicates plugin type uniquely, below 0x1000000
      ('Label', ctypes.c_char_p), # Unique, case-sensitive identifier for the plugin type within the plugin file.
                                  # Must not contain whitespace characters.
      ('Properties', Properties),
      ('Name', ctypes.c_char_p),
      ('Maker', ctypes.c_char_p),
      ('Copyright', ctypes.c_char_p),
      ('PortCount', ctypes.c_ulong),
      ('PortDescriptors', POINTER(PortDescriptor)),
      ('PortNames', POINTER(ctypes.c_char_p)),
      ('PortRangeHints', POINTER(PortRangeHint)),
      ('ImplementationData', ctypes.c_void_p),
      # instantiate(descriptor, sample_rate)
      ('instantiate', CFUNCTYPE(Handle, POINTER(Descriptor), ctypes.c_ulong)),
      ('connect_port', CFUNCTYPE(None, Handle, ctypes.c_ulong, POINTER(Data))),
      ('activate', CFUNCTYPE(None, Handle)),
      # run(handle, samples)
      ('run', CFUNCTYPE(None, Handle, ctypes.c_ulong)),
      # optional, not always set.
      ('run_adding', CFUNCTYPE(None, Handle, ctypes.c_ulong)),
      ('set_run_adding_gain', CFUNCTYPE(None, Handle, Data)),
      ('deactivate', CFUNCTYPE(None, Handle)),
      ('cleanup', CFUNCTYPE(None, Handle)),
    ]

def list_modules(path):
    for base, _, files in os.walk(path):
        for filename in files:
            if filename.endswith('.so'):
                yield os.path.join(base, filename)

def load_module(modname):
    lib = ctypes.cdll.LoadLibrary(modname)
    lib.ladspa_descriptor.restype = POINTER(Descriptor)
    lib.ladspa_descriptor.argtypes = [ctypes.c_ulong]
    return lib
