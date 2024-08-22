import lilv
import ctypes
import sdl2.ext
import urllib.parse
import os
import numpy
import cairo
import cairo_capi
import math
from fractions import Fraction
from entities import Pitch
import entities
import resolution

sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)
main_window = sdl2.ext.Window("mide", (1200,700))

x11_helper = ctypes.CDLL('./x11_helper.so')
get_default_visual = x11_helper.get_default_visual
get_default_visual.restype = ctypes.c_void_p
get_default_visual.argtypes = [ ctypes.c_void_p ]

create_pixmap = x11_helper.create_pixmap
create_pixmap.restype = ctypes.c_void_p
create_pixmap.argtypes = [ ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int ]

copy_pixmap = x11_helper.copy_pixmap
copy_pixmap.restype = None
copy_pixmap.argtypes = [ ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int ]

info = sdl2.syswm.SDL_SysWMinfo()
info.version.major = 2
assert sdl2.syswm.SDL_GetWindowWMInfo(main_window.window, info)
x11_display     = info.info.x11.display
x11_main_window = info.info.x11.window

pixmap = create_pixmap(x11_display, x11_main_window, 1200, 700)
cairo_surf = cairo_capi.xlib_surface_create(
    x11_display, pixmap,
    get_default_visual(x11_display), 1200, 700)
surface = cairo_capi.get_capi().Surface_FromSurface(
    cairo_surf, cairo.XlibSurface)
ctx = cairo.Context(surface)

parent_window = sdl2.ext.Window("mide instrument", (1200,700))

info = sdl2.syswm.SDL_SysWMinfo()
info.version.major = 2
assert sdl2.syswm.SDL_GetWindowWMInfo(parent_window.window, info)
x11_parent = info.info.x11.window

urid_map = {}
uri_map = {}

def get_urid(uri):
    try:
        return urid_map[uri]
    except KeyError:
        urid_map[uri] = u = len(urid_map) + 1
        uri_map[u] = uri
        return u

@lilv.LV2_URID_Map._fields_[1][1]
def urid_map_hook(data, uri):
    u = get_urid(uri.decode("utf-8"))
    #print("URID", uri, u)
    return u
lv2_urid_map = lilv.LV2_URID_Map(None, urid_map_hook)

urid_map_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/ext/urid#map",
    ctypes.cast(ctypes.pointer(lv2_urid_map),
                ctypes.c_void_p))

bounded_block_length_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/ext/buf-size#boundedBlockLength",
    None)

block_length = 1024
block_length_a = (ctypes.c_int64 * 1)(block_length)

scale_factor_a = (ctypes.c_float * 1)(1.10) # 1.15 for dexed, 1.2 for surge xt
options_list = (lilv.LV2_Options_Option * 6)(
  lilv.LV2_Options_Option(
    lilv.LV2_OPTIONS_INSTANCE,
    0,
    get_urid("http://lv2plug.in/ns/ext/buf-size#minBlockLength"),
    ctypes.sizeof(ctypes.c_int32),
    get_urid("http://lv2plug.in/ns/ext/atom#Int"),
    ctypes.cast(block_length_a, ctypes.c_void_p)),
  lilv.LV2_Options_Option(
    lilv.LV2_OPTIONS_INSTANCE,
    0,
    get_urid("http://lv2plug.in/ns/ext/buf-size#maxBlockLength"),
    ctypes.sizeof(ctypes.c_int32),
    get_urid("http://lv2plug.in/ns/ext/atom#Int"),
    ctypes.cast(block_length_a, ctypes.c_void_p)),
  lilv.LV2_Options_Option(
    lilv.LV2_OPTIONS_INSTANCE,
    0,
    get_urid("http://lv2plug.in/ns/extensions/ui#scaleFactor"),
    ctypes.sizeof(ctypes.c_float),
    get_urid("http://lv2plug.in/ns/ext/atom#Float"),
    ctypes.cast(scale_factor_a, ctypes.c_void_p)),
  lilv.LV2_Options_Option(
    lilv.LV2_OPTIONS_INSTANCE,
    0,
    0,
    0,
    0,
    None)
  )

options_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/ext/options#options",
    ctypes.cast(options_list, ctypes.c_void_p))

world = lilv.World()
ns = world.ns
world.load_all()

for i in world.get_all_plugins():
    print(i.get_uri())
    #for ui in i.get_uis():
    #    print(" " + str(ui.get_binary_uri()))

uri = "https://surge-synthesizer.github.io/lv2/surge-xt"
#uri = "https://github.com/asb2m10/dexed.git"
dexed_uri = world.new_uri(uri)
#dexed_uri = world.new_uri("https://github.com/asb2m10/dexed.git")
dexed = world.get_all_plugins()[dexed_uri]

binaries = []
for ui in dexed.get_uis():
    print(ui.get_binary_uri())
    uri = str(ui.get_binary_uri())
    binaries.append(uri)
    #for cl in ui.get_classes():
    #    print(cl)

binary_uri = binaries[0]
parsed_uri = urllib.parse.urlparse(binary_uri)
binary_path = os.path.abspath(
      os.path.join(parsed_uri.netloc, 
        urllib.parse.unquote(parsed_uri.path)))

gui = ctypes.CDLL(binary_path)
gui.lv2ui_descriptor.restype = ctypes.POINTER(lilv.LV2UI_Descriptor)
gui.lv2ui_descriptor.argtypes = [ctypes.c_uint32]

descs = []
desc = gui.lv2ui_descriptor(0)
i = 1
while desc:
    descs.append(desc)
    desc = gui.lv2ui_descriptor(i)
    i += 1

reo = world.new_uri("https://lv2plug.in/ns/ext/options#requiredOption")
print("related")
for opts in dexed.get_related(reo):
    print(opts)
print("required")
for feat in dexed.get_required_features():
    print(feat)
print("optional")
for feat in dexed.get_optional_features():
    print(feat)
features = (ctypes.POINTER(lilv.LV2_Feature) * 4)(
  ctypes.pointer(urid_map_ft),
  ctypes.pointer(bounded_block_length_ft),
  ctypes.pointer(options_ft),
  None)
instance = lilv.Instance(dexed, 48000.0, features)

instance.activate()

LV2_STATE_IS_POD = 1 << 0
LV2_STATE_IS_PORTABLE = 1 << 1
LV2_STATE_IS_NATIVE = 1 << 2

LV2_STATE_SUCCESS = 0
LV2_STATE_ERR_UNKNOWN = 1
LV2_STATE_ERR_BAD_TYPE = 2
LV2_STATE_ERR_BAD_FLAGS = 3
LV2_STATE_ERR_NO_FEATURE = 4
LV2_STATE_ERR_NO_PROPERTY = 5
LV2_STATE_ERR_NO_SPACE = 6

LV2_State_Handle = ctypes.POINTER(None)
LV2_State_Store_Function = ctypes.CFUNCTYPE(ctypes.c_int,
    LV2_State_Handle,
    ctypes.c_uint32, # key
    ctypes.c_void_p, # value
    ctypes.c_size_t, # size
    ctypes.c_uint32, # type
    ctypes.c_uint32) # flags
LV2_State_Retrieve_Function = ctypes.CFUNCTYPE(ctypes.POINTER(None),
    LV2_State_Handle,
    ctypes.c_uint32, # key
    ctypes.POINTER(ctypes.c_size_t), # size
    ctypes.POINTER(ctypes.c_uint32), # type
    ctypes.POINTER(ctypes.c_uint32)) # flags
class LV2_State_Interface(ctypes.Structure):
    _fields_ = [
        ('save', ctypes.CFUNCTYPE(ctypes.c_int, lilv.LV2_Handle,
                           LV2_State_Store_Function,
                           LV2_State_Handle,
                           ctypes.c_uint32,
                           ctypes.POINTER(ctypes.POINTER(lilv.LV2_Feature)))),
        ('restore', ctypes.CFUNCTYPE(ctypes.c_int, lilv.LV2_Handle,
                              LV2_State_Retrieve_Function,
                              LV2_State_Handle,
                              ctypes.c_uint32,
                              ctypes.POINTER(ctypes.POINTER(lilv.LV2_Feature)))),
    ]
lv2_state = instance.instance[0].lv2_descriptor[0].extension_data(
  b"http://lv2plug.in/ns/ext/state#interface")
lv2_state = ctypes.cast(lv2_state, ctypes.POINTER(LV2_State_Interface))

document = entities.load_document('document.mide.zip')

if len(document.instrument.patch) > 0:
    custom_data = None
    @LV2_State_Retrieve_Function
    def retrieve_hook(_, key, size_p, type_p, flags_p):
        global custom_data
        flags_p[0] = LV2_STATE_IS_POD | LV2_STATE_IS_PORTABLE
        name = uri_map[key]
        if name not in document.instrument.patch:
            print(f"{name} not found")
            return None
        print(f"{name} found")
        pd = document.instrument.patch[name]
        type_p[0] = get_urid(pd['type'])
        data = document.instrument.data[pd['path']]
        size_p[0] = len(data)
        custom_data = (ctypes.c_char * len(data))(*data)
        return ctypes.addressof(custom_data)
    k = lv2_state[0].restore(instance.get_handle(),
                         retrieve_hook,
                         None,
                         LV2_STATE_IS_POD | LV2_STATE_IS_PORTABLE,
                         None)
    print(f'restore status: {k}')

audio_input_buffers = []
audio_output_buffers = []
control_input_buffers = []
control_output_buffers = []
midi_inputs = []
midi_outputs = []
for index in range(dexed.get_num_ports()):
  port = dexed.get_port_by_index(index)
  print(port.get_name())
  for cls in port.get_classes():
      print(cls)
  for prt in port.get_properties():
      print(prt)
  if port.is_a(world.ns.lv2.InputPort):
      if port.is_a(world.ns.lv2.AudioPort):
          audio_input_buffers.append(
            numpy.array([0] * block_length, numpy.float32))
          instance.connect_port(index, audio_input_buffers[-1])
      elif port.is_a(world.ns.lv2.ControlPort):
          control_input_buffers.append(
            numpy.array([0], numpy.float32))
          instance.connect_port(index, control_input_buffers[-1])
      elif port.is_a(world.ns.atom.AtomPort):
          if port.supports_event("http://lv2plug.in/ns/ext/midi#MidiEvent"):
              data = (ctypes.c_char * 16384)()
              seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
              #seq = lilv.LV2_Atom_Sequence()
              seq[0].atom.size = 8
              seq[0].atom.type = get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
              seq[0].body.unit = get_urid('https://lv2plug.in/ns/ext/time#beat')
              seq[0].body.pad  = 0
              instance.connect_port(index, ctypes.pointer(data))
              midi_inputs.append(data)
          else:
              print("some other atom input port")
      else:
          print("some other input port")
  elif port.is_a(world.ns.lv2.OutputPort):
      if port.is_a(world.ns.lv2.AudioPort):
          audio_output_buffers.append(
            numpy.array([0] * block_length, numpy.float32))
          instance.connect_port(index, audio_output_buffers[-1])
      elif port.is_a(world.ns.lv2.ControlPort):
          control_output_buffers.append(
            numpy.array([0], numpy.float32))
          instance.connect_port(index, control_output_buffers[-1])
      elif port.is_a(world.ns.atom.AtomPort):
          #if port.supports_event("http://lv2plug.in/ns/ext/midi#MidiEvent"):
              data = (ctypes.c_char * 16384)()
              seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
              #seq = lilv.LV2_Atom_Sequence()
              seq[0].atom.size = 8
              seq[0].atom.type = get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
              seq[0].body.unit = get_urid('https://lv2plug.in/ns/ext/time#beat')
              seq[0].body.pad  = 0
              instance.connect_port(index, ctypes.pointer(data))
              #seq = lilv.LV2_Atom_Sequence()
              #seq.atom.size = 0
              #seq.atom.type = get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
              #instance.connect_port(index, seq)
              midi_outputs.append(data)
          #else:
          #    print("some other atom output port")
      else:
          print(port.get_name())
          for cl in port.get_classes():
              print(cl)
          for cl in port.get_properties():
              print(cl)
          print(dir(port))
          print(world.ns.atom)
          print("some other output port")
  else:
      print("some other port")

control_input_buffers[-1][0] = 1.0 # Enabled

# ui access
desc = descs[0]
print('attempting to open ui')
def write_function(*argv):
    print(argv)
    return None

write_function_hook = lilv.LV2UI_Write_Function(write_function)

instance_access_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/ext/instance-access",
    instance.get_handle())

ui_parent_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/extensions/ui#parent",
    ctypes.cast(x11_parent, ctypes.c_void_p))

ui_idle_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/extensions/ui#idleInterface",
    None)

LV2UI_Feature_Handle = ctypes.c_void_p

ResizeHandler = ctypes.CFUNCTYPE(
  ctypes.c_int,
  LV2UI_Feature_Handle,
  ctypes.c_int,
  ctypes.c_int)
class LV2_Resize(ctypes.Structure):
    _fields_ = [
       ('handle', ctypes.c_void_p),
       ('ui_resize', ResizeHandler) ]

@ResizeHandler
def resize_hook(_, width, height):
    sdl2.video.SDL_SetWindowSize(parent_window.window, width, height)
    return 0

rez = LV2_Resize(None, resize_hook)
resize_ft = lilv.LV2_Feature(
    b"http://lv2plug.in/ns/extensions/ui#resize",
    ctypes.cast(ctypes.pointer(rez), ctypes.c_void_p))

ui_features = (ctypes.POINTER(lilv.LV2_Feature) * 8)(
  ctypes.pointer(urid_map_ft),
  ctypes.pointer(bounded_block_length_ft),
  ctypes.pointer(options_ft),
  ctypes.pointer(instance_access_ft),
  ctypes.pointer(ui_parent_ft),
  ctypes.pointer(resize_ft),
  ctypes.pointer(ui_idle_ft),
  None)

out_widget = (ctypes.c_void_p*1)()

parent_window.show()

ui_handle = desc[0].instantiate(desc,
  uri.encode('utf-8'),
  binary_path.encode('utf-8'),
  write_function_hook,
  None, # controller
  out_widget,
  ui_features) # features
print("ui handle", ui_handle)

class LV2UI_Idle_Interface(ctypes.Structure):
    _fields_ = [('idle', ctypes.CFUNCTYPE(None, lilv.LV2UI_Handle))]

ui_idle = desc[0].extension_data(b"http://lv2plug.in/ns/extensions/ui#idleInterface")
ui_idle = ctypes.cast(ui_idle, ctypes.POINTER(LV2UI_Idle_Interface))

main_window.show()

active_windows = set([parent_window, main_window])

MIDI_Event = get_urid('http://lv2plug.in/ns/ext/midi#MidiEvent')
time_beat = get_urid('https://lv2plug.in/ns/ext/time#beat')

sdl2.SDL_AudioInit(None)

midi_events = []
def push_midi_event(evt):
    midi_events.append(evt)

def stream_midi_event(evt):
    data = midi_inputs[0]
    base = ctypes.addressof(data)
    offset = (ctypes.c_uint32*2).from_address(base)[0]
    # just in case it changes.
    (ctypes.c_uint32*2).from_address(base)[1] = get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
    (ctypes.c_uint32*2).from_address(base+8+0)[0] = time_beat # unit, pad
    offset = ((offset + 7) & ~7) # pad it to 64 bits
    next_event = base + 8 + offset
    
    (ctypes.c_double*1).from_address(next_event)[0] = 0.0 # beat (base 8+8)
    (ctypes.c_uint32*1).from_address(next_event+8)[0] = len(evt) # size
    (ctypes.c_uint32*1).from_address(next_event+12)[0] = MIDI_Event # type
    buf = (ctypes.c_char*len(evt)).from_address(next_event+16)
    for i, byte in enumerate(evt):
        buf[i] = byte
    # calculate size
    (ctypes.c_uint32*2).from_address(base)[0] = offset + 16 + len(evt)

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

bpm = LinearEnvelope([ (0, 80, -2),
                       (4*3, 10, 0) ])
assert bpm.check_positiveness()

print('bpm problem')
print(bpm.area(1.0, 0.5, lambda bpm: 60 / bpm))

class Transport:
    def __init__(self):
        self.time = 0.0
        self.active_voices = set()

class ActiveVoice:
    def __init__(self, voice, beat=0.0, current=-1, next_vg=0.0):
        self.voice = voice
        self.beat = beat
        self.current = current
        self.next_vg = next_vg
        self.notes_on = []

transport = Transport()
transport.active_voices.update(map(ActiveVoice, document.track.voices))

@sdl2.SDL_AudioCallback
def audio_hook(_, stream, length):
    evts = list(midi_events)
    midi_events.clear()
    for evt in evts:
        stream_midi_event(evt)

    now = sdl2.SDL_GetTicks64() / 1000.0

    still_active = set()
    for av in transport.active_voices:
        if av.current == -1: # new voice
            av.current = 0
            av.next_vg = now + bpm.area(av.beat,
                                        float(av.voice[0].duration),
                                        lambda bpm: 60 / bpm)
            av.beat += float(av.voice[0].duration)
            #av.next_vg = now + float(av.voice[0].duration) * (60 / bpm)
            for note in av.voice[0].notes:
                mp = resolution.resolve_pitch(note)
                stream_midi_event([0x90, mp, 0xFF])
                av.notes_on.append(mp)
            still_active.add(av)
        elif av.next_vg <= now:
                # note off messages
                for mp in av.notes_on:
                    stream_midi_event([0x80, mp, 0xFF])
                av.notes_on = []
                # note on messages
                if av.current + 1 < len(av.voice):
                    av.next_vg += bpm.area(av.beat,
                                           float(av.voice[av.current+1].duration),
                                           lambda bpm: 60 / bpm)
                    av.beat += float(av.voice[av.current+1].duration)
                    # av.next_vg += float(av.voice[av.current+1].duration) * (60 / bpm)
                    for note in av.voice[av.current+1].notes:
                        mp = resolution.resolve_pitch(note)
                        stream_midi_event([0x90, mp, 0xFF])
                        av.notes_on.append(mp)
                    still_active.add(av)
                av.current += 1
        else:
            still_active.add(av)

    transport.time = now

    instance.run(block_length)
    data = numpy.dstack(audio_output_buffers[:2]).flatten()
    ctypes.memmove(stream, data.ctypes.data, min(block_length*8, length))

    # Reset the midi input list
    data = midi_inputs[0]
    seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
    seq[0].atom.size = 8
    seq[0].atom.type = get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
    seq[0].body.unit = get_urid('https://lv2plug.in/ns/ext/time#beat')
    seq[0].body.pad  = 0

    #print(midi_outputs[0].raw)

wanted = sdl2.SDL_AudioSpec(48000, sdl2.AUDIO_F32, 2, block_length)
wanted.callback = audio_hook
wanted.userdata = None

k = sdl2.SDL_OpenAudio(ctypes.byref(wanted), None)
print("audio: ", k)

for key in urid_map:
    print(key)

sdl2.SDL_PauseAudio(0)

class Hit:
    def __init__(self, children=None):
        self.children = children or []
        self.on_hover = lambda x, y: None
        self.on_button_down = lambda x, y, button: None
        self.on_button_up = lambda x, y, button: None
    def append(self, item):
        self.children.append(item)

    def extend(self, items):
        self.children.extend(items)

    def hit(self, x, y):
        if self.test(x, y):
            selection = self
            for child in self.children:
                selection = child.hit(x, y) or selection
            return selection

    def test(self, x, y):
        return True

class Circle(Hit):
    def __init__(self, x, y, radius, children=None):
        Hit.__init__(self, children)
        self.x = x
        self.y = y
        self.radius = radius

    def test(self, x, y):
        dx = self.x - x
        dy = self.y - y
        return math.sqrt(dx*dx + dy*dy) <= self.radius

class Box(Hit):
    def __init__(self, x, y, width, height, children=None):
        Hit.__init__(self, children)
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def test(self, x, y):
        ix = self.x <= x < self.x + self.width
        iy = self.y <= y < self.y + self.height
        return ix and iy

class History:
    def __init__(self, document):
        self.document = document
        self.undo_stack = []
        self.redo_stack = []

    def do(self, command):
        self.redo_stack.clear()
        command.do(self.document)
        self.undo_stack.append(command)

    def undo(self):
        command = self.undo_stack.pop()
        command.undo(self.document)
        self.redo_stack.append(command)

    def redo(self):
        command = self.redo_stack.pop()
        command.do(self.document)
        self.undo_stack.append(command)
         
def history_toolbar(history, ctx, hit):
    ctx.select_font_face('FreeSerif')
    ctx.set_font_size(24)
    box = Box(100, 10, 32, 32)
    hit.append(box)
    if len(history.undo_stack) > 0:
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        def f(x, y, button):
            history.undo()
            return True
        box.on_button_down = f
    else:
        ctx.set_source_rgba(0.7, 0.7, 0.7, 1.0)
    ctx.rectangle(100, 10, 32, 32)
    ctx.stroke()
    symbol = chr(0x21B6)
    xt = ctx.text_extents(symbol)
    ctx.move_to(100+15-xt.width/2-xt.x_bearing, 32)
    ctx.show_text(symbol)
    box = Box(133, 10, 32, 32)
    hit.append(box)
    if len(history.redo_stack) > 0:
        ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        def f(x, y, button):
            history.redo()
            return True
        box.on_button_down = f
    else:
        ctx.set_source_rgba(0.7, 0.7, 0.7, 1.0)
    ctx.rectangle(133, 10, 32, 32)
    ctx.stroke()
    symbol = chr(0x21B7)
    xt = ctx.text_extents(symbol)
    ctx.move_to(133+16-xt.width/2-xt.x_bearing, 32)
    ctx.show_text(symbol)
    ctx.set_font_size(12)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
    if len(history.undo_stack) > 0:
        ctx.move_to(166+10, 22)
        ctx.show_text(f"undo: {history.undo_stack[-1].name}")
    if len(history.redo_stack) > 0:
        ctx.move_to(166+10, 36)
        ctx.show_text(f"redo: {history.redo_stack[-1].name}")

history = History(document)
hit_root = Hit()
main_window_id = sdl2.SDL_GetWindowID(main_window.window)
parent_window_id = sdl2.SDL_GetWindowID(parent_window.window)

line = 120
split_index = 0
place = 0
leveys = 80

class DemoCommand:
    def __init__(self):
        self.name = "demo command added during init"
    def do(self, document):
        print('done')
    def undo(self, document):
        print('undone')

history.do(DemoCommand())

running = True
expose = True
while running:
    t = sdl2.SDL_GetTicks64() / 1000.0

    ui_idle[0].idle(ui_handle)

    if main_window in active_windows and expose:
        expose = False
        hit_root = Hit()
        c = Circle(20, 20, 10)
        def clicker(x, y, button):
            print('clicked on circle')
            transport.active_voices.update(map(ActiveVoice, document.track.voices))
        c.on_button_down = clicker
        hit_root.append(c)
        c = Box(300, 300, 250, 250)
        def clicker(x, y, button):
            print('clicked on box')
        c.on_button_down = clicker
        hit_root.append(c)

        ctx.select_font_face('sans-serif')
        ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        ctx.rectangle(0, 0, 1200, 700)
        ctx.fill()

        ctx.set_source_rgba(0, 0, 0, 1.0)
        ctx.arc(20, 20, 10, 0, 2*math.pi)
        ctx.stroke()

        history_toolbar(history, ctx, hit_root)
        ctx.set_source_rgba(0.75, 0.75, 0.75, 1.0)
        for y in range(100, 150, 10):
          ctx.move_to(10, y)
          ctx.line_to(1190, y)
        for y in range(160, 210, 10):
          ctx.move_to(10, y)
          ctx.line_to(1190, y)
        ctx.stroke()
        ctx.set_source_rgba(0.75, 0.75, 0.75, 1.0)
        ctx.arc(50, 150, 5, 0, 2*math.pi)
        ctx.fill()
        ctx.set_font_size(20)
        text = "C4"
        ext = ctx.text_extents(text)
        ctx.move_to(57, 150 - ext.y_bearing/2)
        ctx.show_text(text)
        bar = 57 + ext.width + 2
        ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        ctx.set_font_size(12)
        ctx.move_to(bar, 100-4)
        ctx.show_text('1')
        ctx.move_to(bar, 100)
        ctx.line_to(bar, 200)
        ctx.stroke()
        x = bar + 20
        #bar = x + 40 * 4 - 20
        #ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        #ctx.move_to(bar, 100)
        #ctx.line_to(bar, 200)
        #ctx.stroke()
        #bar = x + 40 * 8 - 20
        #ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
        #ctx.move_to(bar, 100)
        #ctx.line_to(bar, 200)
        #ctx.stroke()
        beats_in_measure = 4
        def plot_vg(notes, duration, p, this_index):
                base, dots, triplet = resolution.categorize_note_duration(duration / 4)
                spacing = {
                    Fraction(2,1): 12,
                    Fraction(1,1): 7,
                    Fraction(1,2): 5,
                    Fraction(1,4): 2,
                    Fraction(1,8): 1,
                    Fraction(1,16): 1,
                    Fraction(1,32): 1,
                    Fraction(1,64): 1,
                    Fraction(1,128): 1,
                }
                if len(notes) == 0:
                    #ctx.set_font_size(9)
                    #ctx.move_to(x + p, 150)
                    #ctx.show_text(str(duration / 4))
                    ctx.select_font_face('FreeSerif')
                    ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
                    ctx.set_font_size(50)
                    ctx.move_to(x + p - 4, 140-2)
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
                    ctx.select_font_face('sans-serif')
                    if triplet:
                        ctx.move_to(x + p, 135)
                        ctx.line_to(x + p + 5, 135 + 5)
                        ctx.line_to(x + p + 5, 135 - 5)
                        ctx.line_to(x + p, 135)
                        ctx.stroke()
                    for dot in range(dots):
                        ctx.arc(x + p + 16 + dot*5, 135 + 3, 2, 0, 2*math.pi)
                        ctx.fill()
                for note in notes:
                    rel_y = 32 - note.position
                    rel_x = p
                    ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
                    if note.accidental is not None:
                        char_accidental = {
                          -2: chr(119083),
                          -1: chr(0x266d),
                           0: chr(0x266e),
                          +1: chr(0x266f),
                          +2: chr(119082),
                        }
                        ctx.select_font_face('FreeSerif')
                        ctx.set_font_size(25)
                        xt = ctx.text_extents(char_accidental[note.accidental])
                        ctx.move_to(x + rel_x - 8 - xt.width, 150 + rel_y*5 + 5)
                        ctx.show_text(char_accidental[note.accidental])
                        ctx.select_font_face('sans-serif')
                    if triplet:
                        ctx.move_to(x + rel_x-5, 150 + rel_y*5)
                        ctx.line_to(x + rel_x+5, 150 + rel_y*5 + 5)
                        ctx.line_to(x + rel_x+5, 150 + rel_y*5 - 5)
                    else:
                        ctx.move_to(x + rel_x+5, 150 + rel_y*5)
                        ctx.arc(x + rel_x, 150 + rel_y*5, 5, 0, 2*math.pi)
                    if base >= Fraction(1, 2):
                        ctx.stroke()
                    else:
                        ctx.fill()
                    for dot in range(dots):
                        ctx.arc(x + rel_x + 8 + dot*5, 150 + rel_y*5 + 3, 2, 0, 2*math.pi)
                        ctx.fill()
                if len(notes) > 0:
                    high = min(150 + (32 - n.position)*5 for n in notes)
                    low = max(150 + (32 - n.position)*5 for n in notes)
                    if high < low:
                        ctx.move_to(x + rel_x + 5, high)
                        ctx.line_to(x + rel_x + 5, low)
                        ctx.stroke()
                    if base <= Fraction(1, 2):
                        ctx.move_to(x + rel_x + 5, high)
                        ctx.line_to(x + rel_x + 5, high - 30)
                        ctx.stroke()
                    for k in range(5):
                        if base <= Fraction(1, 2**(k+3)):
                            ctx.move_to(x + rel_x + 5, high - 30 + k * 4)
                            ctx.line_to(x + rel_x + 5 + 5, high - 30 + k * 4 + 8)
                            ctx.stroke()
                #ctx.set_source_rgba(1,0,0,0.2)
                #ctx.rectangle(x + p, 85, spacing[base] * 20 + 20, 135)
                #ctx.fill()
                box = Box(x+p - 20, 85, spacing[base] * 20 + 20, 135)
                t = x
                def h(_, __):
                    global split_index, place, leveys
                    split_index = this_index
                    place = t + p - 20
                    leveys = spacing[base] * 20 + 20
                    return True
                box.on_hover = h
                hit_root.append(box)
                return spacing[base] * 20 + 20
        for voice in document.track.voices:
            p = 0
            beat_phase = 0
            bar_index = 2
            for ti, vg in enumerate(voice):
                duration = vg.duration
                while beat_phase + duration > 4:
                    t = p
                    thisd = 4 - beat_phase
                    duration -= thisd
                    p += plot_vg(vg.notes, thisd, p, ti)
                    beat_phase = (beat_phase + thisd) % beats_in_measure
                    if beat_phase == 0:
                        bar = x + p - 20
                        ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
                        ctx.set_font_size(12)
                        ctx.move_to(bar, 100-4)
                        ctx.show_text(str(bar_index))
                        bar_index += 1
                        ctx.move_to(bar, 100)
                        ctx.line_to(bar, 200)
                        ctx.stroke()
                    for note in vg.notes:
                        ctx.set_source_rgba(0.2, 0.2, 0.2, 1.0)
                        rel_y = 32 - note.position
                        ctx.move_to(x+t+8, 150 + rel_y*5 + 3)
                        ctx.curve_to(x+t+8, 158 + rel_y*5 + 3,
                                     x+p-8, 158 + rel_y*5 + 3,
                                     x+p-8, 150 + rel_y*5 + 3)
                        ctx.stroke()
                p += plot_vg(vg.notes, duration, p, ti)
                beat_phase = (beat_phase + duration) % beats_in_measure
                if beat_phase == 0:
                    bar = x + p - 20
                    ctx.set_source_rgba(0.75, 0.75, 0.75, 0.5)
                    ctx.set_font_size(12)
                    ctx.move_to(bar, 100-4)
                    ctx.show_text(str(bar_index))
                    bar_index += 1
                    ctx.move_to(bar, 100)
                    ctx.line_to(bar, 200)
                    ctx.stroke()

        total = document.track.voices[0][split_index].duration / 4
        ctx.set_source_rgba(1,1,1,1)
        ctx.rectangle(place, 100, leveys, 100)
        ctx.fill()
        ctx.set_source_rgba(0,0,0,1)
        ctx.rectangle(place, 100, leveys, 100)
        ctx.stroke()
        ctx.set_source_rgba(0.7,0.7,0.7,1)
        ctx.move_to(line, 100)
        ctx.line_to(line, 100+100)
        ctx.stroke()
        ctx.set_source_rgba(0,0,0,1)
        h = Box(place, 100, leveys, 100)
        def f(x, y):
            global line
            ia = resolution.quantize_fraction((x - place) / leveys * float(total))
            ib = total - ia
            if ib in resolution.generate_all_note_durations():
                line = x
                return True
        h.on_hover = f
        def g(x,y,button):
            ia = resolution.quantize_fraction((line - place) / leveys * float(total))
            ib = total - ia
            if ib in resolution.generate_all_note_durations():
                print('splitting')
                n1 = list(document.track.voices[0][split_index].notes)
                n2 = list(document.track.voices[0][split_index].notes)
                document.track.voices[0][split_index:split_index+1] = [
                    VoiceGlyph(n1, ia * 4),
                    VoiceGlyph(n2, ib * 4),
                ]
                return True
        h.on_button_down = g
        hit_root.append(h)

        a = resolution.quantize_fraction((line - place) / leveys * float(total))
        b = total - a
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
        if b in resolution.generate_all_note_durations():
            ctx.select_font_face('FreeSerif')
            ctx.set_font_size(25)
            base, dots, triplet = resolution.categorize_note_duration(a)
            ctx.move_to(place + 5, 100 + 30)
            ctx.show_text(tab[base] + '.'*dots)
            ctx.set_font_size(12)
            ctx.move_to(place + 5, 100 + 42)
            ctx.show_text('3'*int(triplet))
            ctx.set_font_size(25)
            base, dots, triplet = resolution.categorize_note_duration(b)
            text = tab[base] + '.'*dots
            ex = ctx.text_extents(text)
            ctx.move_to(place + leveys - 5 - ex.width, 100 + 30)
            ctx.show_text(text)
            ctx.set_font_size(12)
            ctx.move_to(place + leveys - 5 - ex.width, 100 + 42)
            ctx.show_text('3'*int(triplet))

        surface.flush()
        copy_pixmap(x11_display, pixmap, x11_main_window, 1200, 700)

    for w in active_windows:
        w.refresh()

    sdl2.SDL_Delay(20)

    events = sdl2.ext.get_events()
    for event in events:
        if event.type == sdl2.SDL_QUIT:
            running = False
            break
        elif event.type == sdl2.SDL_WINDOWEVENT_EXPOSED:
            expose = True
        elif event.type == sdl2.SDL_MOUSEMOTION:
            if event.motion.windowID == main_window_id:
                x = event.motion.x
                y = event.motion.y
                expose = expose or hit_root.hit(x, y).on_hover(x,y)
        elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
            if event.button.windowID == main_window_id:
                x = event.button.x
                y = event.button.y
                expose = expose or hit_root.hit(x, y).on_button_down(x,y,event.button.button)
        elif event.type == sdl2.SDL_MOUSEBUTTONUP:
            if event.button.windowID == main_window_id:
                x = event.button.x
                y = event.button.y
                expose = expose or hit_root.hit(x, y).on_button_up(x,y,event.button.button)
        elif event.type == sdl2.SDL_KEYDOWN:
            if event.key.repeat == 0:
                push_midi_event([0x91, 30 + event.key.keysym.scancode, 0xFF])
        elif event.type == sdl2.SDL_KEYUP:
            push_midi_event([0x81, 30 + event.key.keysym.scancode, 0xFF])
        elif event.type == sdl2.SDL_WINDOWEVENT:
            if event.window.event == sdl2.video.SDL_WINDOWEVENT_CLOSE:
                i = event.window.windowID
                if i == main_window_id:
                    surface.finish()
                    main_window.close()
                    active_windows.discard(main_window)
                if i == parent_window_id:
                    document.instrument.patch = {}
                    document.instrument.data = {}
                    @LV2_State_Store_Function
                    def store_hook(_, key, value, size, ty, flags):
                        if not (flags & LV2_STATE_IS_POD):
                            return LV2_STATE_ERR_BAD_FLAGS
                        data = ctypes.cast(value, ctypes.POINTER(ctypes.c_char))
                        identifier = len(document.instrument.data)
                        filename = f'instrument{identifier}.patch'
                        document.instrument.patch[ uri_map[key] ] = {
                            'type': uri_map[ty],
                            'path': filename
                        }
                        document.instrument.data[filename] = data[:size]
                        return LV2_STATE_SUCCESS
                    lv2_state[0].save(instance.get_handle(),
                       store_hook,
                       None,
                       (LV2_STATE_IS_POD | LV2_STATE_IS_PORTABLE),
                       None)
                    entities.save_document('document.mide.zip', document)
                    desc[0].cleanup(ui_handle)
                    parent_window.close()
                    active_windows.discard(parent_window)

sdl2.SDL_PauseAudio(1)

print("shitting down")
instance.deactivate()
del instance

sdl2.SDL_AudioQuit()
print("sdl quit")
sdl2.ext.quit()
