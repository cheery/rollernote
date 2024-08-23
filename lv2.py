import lilv
import ctypes
import urllib.parse
import os
import numpy
import sdl2

class Plugins:
    def __init__(self):
        self.world = lilv.World()
        self.ns = self.world.ns
        self.world.load_all()
        self.plugins = set()

    def list_instrument_plugins(self):
        for i in self.world.get_all_plugins():
            if str(i.get_class()) == "http://lv2plug.in/ns/lv2core#InstrumentPlugin":
                yield str(i.get_uri()), str(i.get_name())

    def plugin(self, uri):
        plugin = Plugin(self, uri)
        self.plugins.add(plugin)
        return plugin

class Plugin:
    def __init__(self, plugins, uri):
        self.widget = None
        self.plugins = plugins
        self.uri = uri
        self.features = Features()
        self.urid_map = dict()
        self.uri_map = dict()
        urid_map_ft = Feature(b"http://lv2plug.in/ns/ext/urid#map")
        urid_map_ft.hook = lilv.LV2_URID_Map._fields_[1][1](self.urid_map_hook)
        urid_map_ft.obj = lilv.LV2_URID_Map(None, urid_map_ft.hook)
        self.features.add(urid_map_ft)
        self.features.add(Feature(b"http://lv2plug.in/ns/ext/buf-size#boundedBlockLength"))
        self.block_length = 1024 # TODO: get the value somehow from audio transport.
        self.block_length_c = (ctypes.c_int64 * 1)(self.block_length)
        
        options_ft = Feature(b"http://lv2plug.in/ns/ext/options#options")
        options_ft.obj = (lilv.LV2_Options_Option * 3)(
            lilv.LV2_Options_Option(
                lilv.LV2_OPTIONS_INSTANCE,
                0,
                self.get_urid("http://lv2plug.in/ns/ext/buf-size#minBlockLength"),
                ctypes.sizeof(ctypes.c_int32),
                self.get_urid("http://lv2plug.in/ns/ext/atom#Int"),
                ctypes.cast(self.block_length_c, ctypes.c_void_p)),
            lilv.LV2_Options_Option(
                lilv.LV2_OPTIONS_INSTANCE,
                0,
                self.get_urid("http://lv2plug.in/ns/ext/buf-size#maxBlockLength"),
                ctypes.sizeof(ctypes.c_int32),
                self.get_urid("http://lv2plug.in/ns/ext/atom#Int"),
                ctypes.cast(self.block_length_c, ctypes.c_void_p)),
            #lilv.LV2_Options_Option(
            #    lilv.LV2_OPTIONS_INSTANCE,
            #    0,
            #    self.get_urid("http://lv2plug.in/ns/extensions/ui#scaleFactor"),
            #    ctypes.sizeof(ctypes.c_float),
            #    self.get_urid("http://lv2plug.in/ns/ext/atom#Float"),
            #    ctypes.cast(scale_factor_a, ctypes.c_void_p)),
            lilv.LV2_Options_Option(lilv.LV2_OPTIONS_INSTANCE, 0, 0, 0, 0, None)
        )
        self.features.add(options_ft)

        uri_c = plugins.world.new_uri(uri)
        self.desc = plugins.world.get_all_plugins()[uri_c]
        self.name = str(self.desc.get_name())
        self.instance = lilv.Instance(self.desc, 48000.0, self.features.array())
        self.instance.activate()

        state = self.instance.instance[0].lv2_descriptor[0].extension_data(
            b"http://lv2plug.in/ns/ext/state#interface")
        self.state = ctypes.cast(state,
                                 ctypes.POINTER(lilv.LV2_State_Interface))

        # TODO: Handle required features.
        # reo = world.new_uri("https://lv2plug.in/ns/ext/options#requiredOption")
        # print("related")
        # for opts in dexed.get_related(reo):
        #     print(opts)
        # print("required")
        # for feat in dexed.get_required_features():
        #     print(feat)
        # print("optional")
        # for feat in dexed.get_optional_features():
        #     print(feat)

        self.audio_inputs = []
        self.audio_outputs = []
        self.control_inputs = {}
        self.control_outputs = {}
        self.inputs = {}
        self.outputs = {}

        for index in range(self.desc.get_num_ports()):
            port = self.desc.get_port_by_index(index)
            name = str(port.get_name())
            if port.is_a(plugins.world.ns.lv2.AudioPort):
                buf = numpy.array([0] * self.block_length, numpy.float32)
                if port.is_a(plugins.world.ns.lv2.InputPort):
                    self.audio_inputs.append((name, buf))
                elif port.is_a(plugins.world.ns.lv2.OutputPort):
                    self.audio_outputs.append((name, buf))
                else:
                    assert False
                self.instance.connect_port(index, buf)
            elif port.is_a(plugins.world.ns.lv2.ControlPort):
                buf = numpy.array([0], numpy.float32)
                if port.is_a(plugins.world.ns.lv2.InputPort):
                    self.control_inputs[name] = buf
                elif port.is_a(plugins.world.ns.lv2.OutputPort):
                    self.control_outputs[name] = buf
                else:
                    assert False
                self.instance.connect_port(index, buf)
            elif port.is_a(plugins.world.ns.atom.AtomPort):
                #if port.supports_event("http://lv2plug.in/ns/ext/midi#MidiEvent"):
                data = (ctypes.c_char * 16384)()
                seq = ctypes.cast(ctypes.pointer(data), ctypes.POINTER(lilv.LV2_Atom_Sequence))
                seq[0].atom.size = 8
                seq[0].atom.type = self.get_urid("http://lv2plug.in/ns/ext/atom#Sequence")
                seq[0].body.unit = self.get_urid('https://lv2plug.in/ns/ext/time#beat')
                seq[0].body.pad  = 0
                if port.is_a(plugins.world.ns.lv2.InputPort):
                    self.inputs[name] = data
                elif port.is_a(plugins.world.ns.lv2.OutputPort):
                    self.outputs[name] = data
                else:
                    assert False
                self.instance.connect_port(index, ctypes.pointer(data))
            else:
                assert False, f'unknown port: {name}'
        self.control_inputs['Enabled'][0] = 1.0

        self.MIDI_Event = self.get_urid('http://lv2plug.in/ns/ext/midi#MidiEvent')
        self.time_beat = self.get_urid('https://lv2plug.in/ns/ext/time#beat')

        # It is advisable to edit values in audio loop.
        self.pending_events = []

    def get_urid(self, uri):
        try:
            return self.urid_map[uri]
        except KeyError:
            self.urid_map[uri] = urid = len(self.urid_map) + 1
            self.uri_map[urid] = uri
            return urid

    def urid_map_hook(self, data, uri):
        return self.get_urid(uri.decode("utf-8"))

    def load(self, patch, data):
        custom_data = None
        @lilv.LV2_State_Retrieve_Function
        def retrieve_hook(_, key, size_p, type_p, flags_p):
            nonlocal custom_data
            flags_p[0] = lilv.LV2_STATE_IS_POD | lilv.LV2_STATE_IS_PORTABLE
            name = self.uri_map[key]
            if name not in patch:
                return None
            pd = patch[name]
            type_p[0] = self.get_urid(pd['type'])
            dt = data[pd['path']]
            size_p[0] = len(dt)
            custom_data = (ctypes.c_char * len(dt))(*dt)
            return ctypes.addressof(custom_data)
        k = self.state[0].restore(
                        self.instance.get_handle(),
                        retrieve_hook,
                        None,
                        lilv.LV2_STATE_IS_POD | lilv.LV2_STATE_IS_PORTABLE,
                        None)
        assert k == 0

    def save(self, name = 'instrument'):
        patch = {}
        data = {}
        @lilv.LV2_State_Store_Function
        def store_hook(_, key, value, size, ty, flags):
            if not (flags & LV2_STATE_IS_POD):
                return LV2_STATE_ERR_BAD_FLAGS
            dt = ctypes.cast(value, ctypes.POINTER(ctypes.c_char))
            identifier = len(data)
            filename = f'{name}.{identifier}.patch'
            patch[ self.uri_map[key] ] = {
                'type': self.uri_map[ty],
                'path': filename
            }
            data[filename] = data[:size]
            return LV2_STATE_SUCCESS
        self.state[0].save(instance.get_handle(),
                           store_hook,
                           None,
                           (lilv.LV2_STATE_IS_POD | lilv.LV2_STATE_IS_PORTABLE),
                           None)
        return patch, data

    def get_ui_binary_path(self):
        binaries = []
        for ui in self.desc.get_uis():
            uri = str(ui.get_binary_uri())
            binaries.append(uri)
        binary_uri = binaries[0]
        parsed_uri = urllib.parse.urlparse(binary_uri)
        binary_path = os.path.abspath(
            os.path.join(parsed_uri.netloc, 
                urllib.parse.unquote(parsed_uri.path)))
        return binary_path

    def push_midi_event(self, data, evt):
        base = ctypes.addressof(data)
        offset = (ctypes.c_uint32*2).from_address(base)[0]
        offset = ((offset + 7) & ~7) # pad it to 64 bits
        next_event = base + 8 + offset
        (ctypes.c_double*1).from_address(next_event)[0] = 0.0 # beat (base 8+8)
        (ctypes.c_uint32*1).from_address(next_event+8)[0] = len(evt) # size
        (ctypes.c_uint32*1).from_address(next_event+12)[0] = self.MIDI_Event # type
        buf = (ctypes.c_char*len(evt)).from_address(next_event+16)
        for i, byte in enumerate(evt):
            buf[i] = byte
        # calculate size
        (ctypes.c_uint32*2).from_address(base)[0] = offset + 16 + len(evt)

    # Wrap input port manipulations into events.
    def event(self, fn):
        self.pending_events.append(fn)

    def close(self):
        self.instance.deactivate()
        del self.instance
        self.plugins.plugins.discard(self)

class Features:
    def __init__(self):
        self.all = []

    def add(self, feature):
        obj = None
        if feature.obj is not None:
            if isinstance(feature.obj, int):
                obj = feature.obj
            else:
                obj = ctypes.cast(ctypes.pointer(feature.obj), ctypes.c_void_p)
        feature.ft = lilv.LV2_Feature(feature.uri, obj)
        self.all.append(feature)

    def array(self):
        return mk_p_array(lilv.LV2_Feature, [f.ft for f in self.all])

class Feature:
    def __init__(self, uri):
        self.uri = uri
        self.obj = None
        self.ft = None

def mk_p_array(ty, items):
    return (ctypes.POINTER(ty) * (1 + len(items)))(*[
        ctypes.pointer(item) for item in items
    ])

class UIPayload:
    def __init__(self, widget, plugin, scale_factor=1.15):
        plugin.widget = widget
        binary_path = plugin.get_ui_binary_path()
        self.plugin = plugin
        self.features = Features()
        for ft in plugin.features.all:
            if ft.uri != b"http://lv2plug.in/ns/ext/options#options":
                self.features.add(ft)

        self.scale_factor_c = (ctypes.c_float * 1)(scale_factor) # 1.15 for dexed, 1.2 for surge xt

        options_ft = Feature(b"http://lv2plug.in/ns/ext/options#options")
        options_ft.obj = (lilv.LV2_Options_Option * 4)(
            lilv.LV2_Options_Option(
                lilv.LV2_OPTIONS_INSTANCE,
                0,
                self.plugin.get_urid("http://lv2plug.in/ns/ext/buf-size#minBlockLength"),
                ctypes.sizeof(ctypes.c_int32),
                self.plugin.get_urid("http://lv2plug.in/ns/ext/atom#Int"),
                ctypes.cast(self.plugin.block_length_c, ctypes.c_void_p)),
            lilv.LV2_Options_Option(
                lilv.LV2_OPTIONS_INSTANCE,
                0,
                self.plugin.get_urid("http://lv2plug.in/ns/ext/buf-size#maxBlockLength"),
                ctypes.sizeof(ctypes.c_int32),
                self.plugin.get_urid("http://lv2plug.in/ns/ext/atom#Int"),
                ctypes.cast(self.plugin.block_length_c, ctypes.c_void_p)),
            lilv.LV2_Options_Option(
                lilv.LV2_OPTIONS_INSTANCE,
                0,
                self.plugin.get_urid("http://lv2plug.in/ns/extensions/ui#scaleFactor"),
                ctypes.sizeof(ctypes.c_float),
                self.plugin.get_urid("http://lv2plug.in/ns/ext/atom#Float"),
                ctypes.cast(self.scale_factor_c, ctypes.c_void_p)),
            lilv.LV2_Options_Option(lilv.LV2_OPTIONS_INSTANCE, 0, 0, 0, 0, None)
        )
        self.features.add(options_ft)

        ia = Feature(b"http://lv2plug.in/ns/ext/instance-access")
        ia.obj = plugin.instance.get_handle()
        self.features.add(ia)
        
        idle_ft = Feature(b"http://lv2plug.in/ns/extensions/ui#idleInterface")
        self.features.add(idle_ft)

        info = sdl2.syswm.SDL_SysWMinfo()
        info.version.major = 2
        assert sdl2.syswm.SDL_GetWindowWMInfo(widget.window.window, info)
        x11_window = info.info.x11.window

        ui_parent_ft = Feature(b"http://lv2plug.in/ns/extensions/ui#parent")
        ui_parent_ft.obj = x11_window
        self.features.add(ui_parent_ft)

        lv2_gui = ctypes.CDLL(binary_path)
        lv2_gui.lv2ui_descriptor.restype = ctypes.POINTER(lilv.LV2UI_Descriptor)
        lv2_gui.lv2ui_descriptor.argtypes = [ctypes.c_uint32]

        # There would be potentially many descriptors,
        # but we choose just the first one.
        self.desc = lv2_gui.lv2ui_descriptor(0)

        self.write_hook_c = lilv.LV2UI_Write_Function(self.write_hook)
        self.resize_hook_c = lilv.LV2_ResizeHandler(self.resize_hook)
        resize_ft = Feature(b"http://lv2plug.in/ns/extensions/ui#resize")
        resize_ft.obj = lilv.LV2_Resize(None, self.resize_hook_c)
        self.features.add(resize_ft)

        self.out_widget = (ctypes.c_void_p*1)()

        self.handle = self.desc[0].instantiate(self.desc,
            plugin.uri.encode('utf-8'),
            binary_path.encode('utf-8'),
            self.write_hook_c,
            None, # controller
            self.out_widget,
            self.features.array())

        idle = self.desc[0].extension_data(b"http://lv2plug.in/ns/extensions/ui#idleInterface")
        self.idle_c = ctypes.cast(idle, ctypes.POINTER(lilv.LV2UI_Idle_Interface))


    def write_hook(self, *argv):
        return None

    def resize_hook(self, _, width, height):
        sdl2.video.SDL_SetWindowSize(self.plugin.widget.window.window, width, height)
        return 0

    def draw(self):
        pass

    def update(self):
        self.idle_c[0].idle(self.handle)

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
        self.desc[0].cleanup(self.handle)
        self.plugin.widget = None
