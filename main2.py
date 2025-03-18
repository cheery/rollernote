# Midiä sämpleiksi nauhoittava soitto-ohjelma
import aural.device
import aural.ladspa

import components3
import mido
import sdl2.ext
import entities
from visual import Widget, process_widgets
#import cairo
from aural import lv2
import aural as audio
#import commands
from visual import gui6
import math
from music import resolution
import bisect
import random
#import components
import subprocess
from fractions import Fraction
import os
#from immutables import Map

def get_tempo_envelope(document):
    default = random.randint(10, 200)
    for graph in document.track.graphs:
        if isinstance(graph, entities.Envelope) and graph.kind == 'tempo':
            env = resolution.linear_envelope(graph.segments, default)
            if env.check_positiveness():
                return env
    return resolution.LinearEnvelope([ (0, default, 0) ])

def setup_playback(document):
    bpm = get_tempo_envelope(document)
    return bpm, document.track.voices, dict((s.uid, s) for s in document.track.graphs)

from reaction import *
from aural import box
from aural.box import On, Off
from aural.miditunes import *
#from components3 import *

#ListInserted = namedtuple('ListInserted', ['index', 'value'])
#ListRemoved  = namedtuple('ListRemoved', ['value'])

#class ListControl:
#    def __init__(self, ui, contents):
#        self.modified = Source(ui.engine, as_stream)
#        self.contents = contents
#
#class ListView(gui3.Detail):
#    def __init__(self, control, func):
#        self.control = control
#        self.func    = func
#        self.table   = dict()
#
#    def attach(self, ui, this):
#        for value in self.control.contents:
#            frame = self.func(self.control, value)
#            this.contents.append(frame)
#            self.table[value] = frame
#        #@ui.engine.observe(self.control.modified)
#        #def _logic_(cmds):
#        #    if not cmds:
#        #        return
#        #    for cmd in cmds.value:
#        #        if isinstance(cmd, Inserted):
#        #            frame = self.func(self.control, cmd.key, dict(cmd.fields))
#        #            this.contents.append(frame)
#        #            self.table[cmd.key] = frame
#        #            frame.attach(ui, this)
#        #            ui.reconstrain()
#        #        if isinstance(cmd, Erased):
#        #            frame = self.table.pop(cmd.key)
#        #            this.contents.remove(frame)
#        #            frame.detach()
#        #            ui.reconstrain()
#
#import pandas as pd
#
#Inserted = namedtuple('Inserted', ['key', 'fields'])
#Erased   = namedtuple('Erased',   ['key'])
#Modified = namedtuple('Modified', ['key', 'name', 'value'])
#
## pd.read_csv(name, dtype=..., index_col=...)
## d.to_csv(name, index_label=...)
#
#class DatasetControl:
#    def __init__(self, ui, dataset):
#        self.modified = Source(ui.engine, as_stream)
#        self.dataset = dataset
#
#class DatasetView(gui3.Detail):
#    def __init__(self, control, func):
#        self.control = control
#        self.func    = func
#        self.table   = dict()
#
#    def attach(self, ui, this):
#        for key in self.control.dataset.index:
#            frame = self.func(self.control, key, dict(self.control.dataset.loc[key]))
#            this.contents.append(frame)
#            self.table[key] = frame
#        @ui.engine.observe(self.control.modified)
#        def _logic_(cmds):
#            if not cmds:
#                return
#            for cmd in cmds.value:
#                if isinstance(cmd, Inserted):
#                    frame = self.func(self.control, cmd.key, dict(cmd.fields))
#                    this.contents.append(frame)
#                    self.table[cmd.key] = frame
#                    frame.attach(ui, this)
#                    ui.reconstrain()
#                if isinstance(cmd, Erased):
#                    frame = self.table.pop(cmd.key)
#                    this.contents.remove(frame)
#                    frame.detach()
#                    ui.reconstrain()
#
#def demo(ui, editor):
#    dc = DatasetControl(ui, )
#
#    def _builder2_(control, key, fields):
#        @collect(control.modified)
#        def this_thing(mods):
#            out = []
#            for mod in mods:
#                if isinstance(mod, Modified) and mod.key == key:
#                    out.append(mod)
#            if out:
#                return Some(out)
#        def _modify_(fs, mods):
#            for mod in mods:
#                fs[mod.name] = mod.value
#            return fs
#        fields = Memory(fields, _modify_, this_thing)
#
#        mouse = gui3.MouseControl(ui)
#        pos = Hold((0,0), mouse.motion)
#        #bas = Hold((0,0), snapshot(mouse.left.down, pos)(lambda _, pos: pos))
#        @gui3.logic(pos,Hold(False,mouse.left.pressed), mouse.right.down)
#        def on_drag(ui, this, xy, pressed, right):
#            if pressed:
#                x, y = xy
#                x0,y0,w,h = this.parent.computed_box
#                x -= x0
#                y -= y0
#                control.modify(key, 'onset', x/800)
#                control.modify(key, 'offset', x/800+0.1)
#                note = y // 3
#                control.modify(key, 'note', max(0, min(127, note)))
#            if right:
#                dc.erase(key)
#        x0 = gui3.Variable()
#        x1 = gui3.Variable()
#        y0 = gui3.Variable()
#        y1 = gui3.Variable()
#        def f0(ui, this, solver, fields):
#            solver.addEditVariable(x0, 'strong')
#            solver.addEditVariable(x1, 'strong')
#            solver.addEditVariable(y0, 'strong')
#            solver.addEditVariable(y1, 'strong')
#            solver.addConstraint(this.left == x0 + this.parent.left)
#            solver.addConstraint(this.right == x1 + this.parent.left)
#            solver.addConstraint(this.top == y0 + this.parent.bottom)
#            solver.addConstraint(this.bottom == y1 + this.parent.bottom)
#        def f1(ui, this, solver, fields):
#            solver.suggestValue(x0, 800 * float(fields['onset']))
#            solver.suggestValue(x1, 800 * float(fields['offset']))
#            solver.suggestValue(y0, 3*(1 + int(fields['note'])))
#            solver.suggestValue(y1, 3*(0 + int(fields['note'])))
#        return gui3.Container([
#            on_drag,
#            gui3.CustomLayout(f0, f1, fields),
#            gui3.Column(),
#            gui3.trace((1,0,0,1)),
#            label(compute(fields)(lambda fields: repr(int(fields['note'])))),
#        ], mouse=mouse)
#    dc_mouse = gui3.MouseControl(ui)
#    pos = Hold((0,0), dc_mouse.motion)
#    @gui3.logic(dc_mouse.left.down, pos)
#    def dc_button(ui, this, left, xy):
#        if left:
#            x, y = xy
#            x -= this.left.value()
#            y -= this.bottom.value()
#            dc.insert({'onset': x/800,
#                       'offset': x/800+0.1,
#                       'note': (y//3),
#                       'velocity': 1.0})
#
#    def sweep_draw_setup(ui):
#        program = ui.mem(gui3.plain_line_program)
#        data = np.full(4, 0.0, dtype=np.float32)
#        buffer = ui.ctx.buffer(data)
#        vao = ui.ctx.vertex_array(program, buffer, 'point')
#        return program, vao, buffer, data
#
#    @gui3.drawing(ui.now)
#    def visualz(ui, this, now):
#        x,y,w,h = this.computed_box
#        t = (now % 5) / 5 * w
#        program, vao, buffer, data = ui.mem(sweep_draw_setup)
#        program['size'] = ui.widget.width, ui.widget.height
#        program['color'] = 1,0,0,1
#        data[0] = x + t
#        data[1] = y
#        data[2] = x + t
#        data[3] = y + h
#        buffer.write(data)
#        vao.render(mode=ui.ctx.LINES)
#        
#    dcv2 = gui3.Container([
#        dc_button,
#        visualz,
#        gui3.trace((0,0,0,1)),
#        gui3.Width(800),
#        gui3.Height(128*3),
#        DatasetView(dc, _builder2_),
#    ], mouse=dc_mouse)
#
#    w = 0.0
#    playing = {}
#    @ui.engine.observe(ui.now)
#    def _player_(now):
#        nonlocal w
#        t = (now % 5) / 5
#        if t < w:
#            w -= 1
#        assert w <= t
#        onsets = dc.dataset
#        for x in range(len(onsets)):
#            m = onsets.iloc[x]
#            onset = m['onset']
#            offset = m['offset']
#            note = m['note']
#            isect = max(w, onset) <= min(t, offset)
#            if not isect:
#                continue
#            offset = (offset - onset) + now
#            if note in playing:
#                playing[note] = max(playing[note], offset)
#            else:
#                playing[note] = offset
#                editor.audio_output.lock()
#                editor.fire_midi_keyboard(ui, On(note, 1.0))
#                editor.audio_output.unlock()
#        for note, offset in list(playing.items()):
#            if offset <= now:
#                playing.pop(note)
#                editor.audio_output.lock()
#                editor.fire_midi_keyboard(ui, Off(note))
#                editor.audio_output.unlock()
#        w = t
#
#    import os
#
#    def filefunc(files, entry):
#        if entry.is_dir():
#            color = (0.2, 0.2, 0.5, 1.0)
#            name = entry.name + "/"
#        else:
#            color = (0,0,0,1)
#            name = entry.name
#        return label(name, color=color, height=16)
#
#    return gui3.Container([
#        dcv2,
#        # textbox(textctl),
#        # button(ui, textctl.text),
#        # gui3.Container([
#        #     gui3.HAlign(0.0),
#        #     gui3.Row(),
#        #     virtual_keyboard(editor, ui),
#        #     oscilloscope(*editor.gui_channels),
#        #     vu_meter(ui, *editor.gui_channels),
#        #     clavier_visualizer(editor.gui_clavier, ui.now),
#        # ]),
#    ], keyboard = gui3.KeyboardControl(ui))

def demo(editor):
    ui = gui5.context.get()
    ui.ctx.enable(ui.ctx.BLEND)
    ui.ctx.blend_equation = ui.ctx.FUNC_ADD
    ui.ctx.blend_func = ui.ctx.SRC_ALPHA, ui.ctx.ONE_MINUS_SRC_ALPHA

    #clock(editor.time, (0,0, 150, 150))
    #gui5.fill((0,1,0,1), (150, 150, 50, 50))
    #gui5.fill((0,1,1,1), (200, 150, 50, 50))
    #gui5.fill((1,0,1,1), (150, 200, 50, 50))

    for index in editor.thing.index:
        fs = editor.thing.loc[index]
        onset  = fs['onset']
        offset = fs['offset']
        note   = fs['note']
        x0 = onset * 800
        x1 = offset * 800
        y0 = note * 8
        rect = (x0, y0, x1-x0, 8)
        gui5.fill((1,0,0,1), rect)
        ident = (50, index)
        if gui5.box(ui.mouse, rect):
            ui.hotitem = ident
            if ui.activeitem is None and ui.buttons == 1:
                ui.activeitem = ident
                ui.activestate = ui.mouse, onset, offset, note
        if ui.activeitem == ident:
            (x,y), onset, offset, note = ui.activestate
            editor.thing.loc[index, 'onset'] = (ui.mouse[0] - x) / 800 + onset
            editor.thing.loc[index, 'offset'] = (ui.mouse[0] - x) / 800 + offset
            nnote = (ui.mouse[1] - y) // 8 + note
            nnote = max(0, min(127, nnote))
            editor.thing.loc[index, 'note'] = nnote

    rect = (0,0,800,128*8)
    gui5.trace((0,0,0,1), rect)

    if gui5.box(ui.mouse, rect):
        ui.hotitem = 50
        if ui.activeitem is None and ui.buttons == 1:
            ui.activeitem = 50
            key = editor.thing.index.max()+1
            editor.thing.loc[key] = {
                'onset': (ui.mouse[0] - 0) / 800,
                'offset': (ui.mouse[0] - 0) / 800 + 0.1,
                'note': (ui.mouse[1] - 0) // 8,
                'velocity': 1.0
            }


# @gui4.composable
# def demo_bar(index, editor):
#     gui4.column(0)
#     gui4.trace((1,0,0,1))
#     note = int(editor.thing.loc[index]['note'])
#     label(repr(note))
# 
# 
# @gui4.composable
# def demo_row1(editor):
#     gui4.trace((1,0,0,1))
#     gui4.row(10)
#     colorbox[0]((0,1,0,1))
#     colorbox[1]((0,1,1,1))
#     colorbox[2]((1,0,1,1))
#     clock(editor.time)
#     scrollinglabel("Hello world", editor.time, 50)
#     testing = button[1]("Testing")
#     testing2 = button[2]("Testing2")
#     virtual_keyboard(editor)
#     oscilloscope(editor.out0, editor.out1)
#     vu_meter(editor.out0, editor.out1)
#     clavier_visualizer(editor)
# 
#     @gui4.logic(testing, testing2)
#     def _custom_logic_(ui, ident, layout, testing, testing2):
#         if testing:
#             print("hello")
#         if testing2:
#             print("world")
# 
# @gui4.composable
# def demo_row2(editor):
#     gui4.trace((1,0,0,1))
#     gui4.row(10)
#     demo_directory(editor)
#     text = gui4.state[1](value="hello")
#     textbox[1](text)
#     demo_thing(editor)
# 
# @gui4.composable
# def demo_directory(editor):
#     gui4.column(5)
#     for entry in editor.directory_contents:
#         if entry.is_dir():
#             color = (0.2, 0.2, 0.5, 1.0)
#             name = entry.name + "/"
#         else:
#             color = (0,0,0,1)
#             name = entry.name
#         label[name](name, color=color, height=16)
# 
# @gui4.composable
# def demo_thing(editor):
#     gui4.trace((0,0,0,1))
#     @gui4.layout
#     def _size_(cn, this):
#         cn(cn[this].width == 800)
#         cn(cn[this].height == 128*3)
#     for index in editor.thing.index:
#         demo_bar[index](index, editor)
#     @gui4.static
#     def layout_contents(layouter, this):
#         x,y,w,h = layouter[this].rect
#         for item in this.subframes:
#             index = item.key[1]
#             fs = editor.thing.loc[index]
#             onset = fs['onset']
#             offset = fs['offset']
#             note = fs['note']
#             layouter[item] = gui4.RigidLayout(int(x + onset*w), int(y + note*3),
#                                              int((offset - onset)*w), 3)
#             layouter.constrain(item)
#     @gui4.logic()
#     def button_press(ui, ident, layout):
#         if ui.inside:
#             ui.hotitem = ident
#             if ui.activeitem is None and ui.buttons > 0:
#                 ui.activeitem = ident
#                 key = editor.thing.index.max()+1
#                 editor.thing.loc[key] = {
#                   'onset': (ui.mouse[0] - layout.left) / layout.width,
#                   'offset': (ui.mouse[0] - layout.left) / layout.width + 0.1,
#                   'note': (ui.mouse[1] - layout.bottom) // 3,
#                   'velocity': 1.0
#                 }
# 
# @gui4.composable
# def demo_bar(index, editor):
#     gui4.column(0)
#     gui4.trace((1,0,0,1))
#     note = int(editor.thing.loc[index]['note'])
#     label(repr(note))
# 
# #        self.next_key = dataset.index.max()+1 if len(dataset) > 0 else 0
# #
# #    def insert(self, fields):
# #        key, self.next_key = self.next_key, self.next_key+1
# #        self.dataset.loc[key] = fields
# #        self.modified.send(Inserted(key, fields))
# #        return key
# #
# #    def erase(self, key):
# #        self.dataset = self.dataset.drop(key)
# #        self.modified.send(Erased(key))
# #
# #    def modify(self, key, name, value):
# #        self.dataset.loc[key, name] = value

class MainApp(gui6.Node):
    def on_signal(self, path, action):
        match action:
            case components3.clicked():
                print("button clicked")
            case _:
                pass

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x, y)
        gui6.fill(ui, (0.2, 0.2, 0.2, 1.0), rect)

import v2.avl
import v2.mid
import v2.rhythm
import v2.music.resolution
import v2.music.notes
import v2.widget

import aural.ladspa

locator = aural.ladspa.Locator()
selection = list(locator.list())

class PrimType:
    pass

signal  = PrimType()
control = PrimType()
clavier = PrimType()

class Pipeline:
    def __init__(self, uid, inputs, pipe, outputs, input_names, output_names):
        self.uid = uid
        self.inputs = inputs
        self.pipe = pipe
        self.outputs = outputs
        self.input_names = input_names
        self.output_names = output_names

class OutPort:
    def __init__(self, uid, ty):
        self.uid = uid
        self.ty  = ty

class Constant:
    def __init__(self, const):
        self.const = const

class Knob:
    def __init__(self, lower, upper, ratio, is_log=False):
        self.lower = lower
        self.upper = upper
        self.is_log = is_log
        self.ratio = ratio

    def get_value(self):
        lower, upper = self.lower, self.upper
        u = self.ratio
        if self.is_log:
            return math.exp(math.log(lower) * u + math.log(upper) * (1-u))
        else:
            return lower * u + upper * (1-u)

def value_knob(lower, upper, value, is_log=False):
    ratio = math.log(value / upper) / math.log(lower / upper)
    return Knob(lower, upper, ratio, is_log=is_log)

class InPort:
    def __init__(self, value, ty):
        self.value = value
        self.ty    = ty

class Template:
    def __init__(self, uid, module, label, inputs, outputs):
        self.uid = uid
        self.module = module
        self.label = label
        self.inputs = inputs
        self.outputs = outputs
        self.desc = locator.load(module, label)
        #print("%.2f" % (self.desc.info['ports'][0]['hint']['lower'] * 44100))
        #print("%.2f" % (self.desc.info['ports'][0]['hint']['upper'] * 44100))

main_pipe = Pipeline(1, 
  inputs = [ OutPort(2, clavier) ],
  pipe = [
      Template(4, "sawtooth_1641", b"sawtooth_fc_oa",
         inputs = [ InPort(value_knob(0.92, 22050, 440.0, is_log=True), control) ],
         outputs = [ OutPort(3, signal) ])
  ],
  outputs = [ InPort(3, signal), InPort(3, signal) ],
  input_names = [ "clavier" ],
  output_names = [ "left", "right" ] )

def color_by_type(ty):
    if ty is control:
        return (1,1,0,1)
    elif ty is signal:
        return (1,0,0,1)
    else:
        return (1,1,1,1)

class GuiPort(gui6.Node):
    def __init__(self, *args, color, value=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.color = color
        self.value = value

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x, y)
        inrect0 = gui6.Rect(rect.left + 4, rect.bottom + 4, rect.width - 8, rect.height - 8)
        inrect1 = gui6.Rect(rect.left + 10, rect.bottom + 10, rect.width - 20, rect.height - 20)
        gui6.fill(ui, (0,0,0,1), rect)
        gui6.trace(ui, self.color, rect)
        if isinstance(self.value, Knob):
            gui6.circle_stroke(ui, (0.5,0.5,0.5,1), inrect0)
            ratio = self.value.ratio
            x = rect.hcenter - math.sin(math.pi*(ratio * 1.5 + 0.25)) * inrect0.width/2
            y = rect.vcenter - math.cos(math.pi*(ratio * 1.5 + 0.25)) * inrect0.height/2
            gui6.circle_fill(ui, (1,1,1,1), (x-2,y-2,4,4))
            hc = rect.hcenter
            vc = rect.vcenter
            value = self.value.get_value()
            if -10 < value < 10.0:
                text = "%.2f" % value
            else: 
                text = "%.1f" % value
            font = ui.mem(FontEngine, int(9))
            width = font.measure(text)
            height = font.ascent + font.descent
            font.prepare((1,1,1,1))
            font.text(text, round(hc - width/2),
                            round(rect.bottom - height + font.descent))
            font.finish()

        else:
            gui6.circle_stroke(ui, self.color, inrect0)
            gui6.circle_fill(ui, self.color, inrect1)

def inport_column(names, ports, inline=False):
    with gui6.Node():
        gui6.flex_direction(gui6.Column)
        if not inline:
            gui6.margin(gui6.Left, 10.0)
            with gui6.Node():
                gui6.height(60)
        for i, port in enumerate(ports):
            with gui6.Node():
                gui6.flex_direction(gui6.Row)
                gui6.align_items(gui6.Center)
                with GuiPort(value=port.value, color=color_by_type(port.ty)):
                    gui6.width(32)
                    gui6.height(32)
                    gui6.margin(gui6.All, 10)
                components3.Label(text=names[i], color=(1,0,1,1), font_height=12)

def outport_column(names, ports, inline=False):
    with gui6.Node():
        gui6.flex_direction(gui6.Column)
        gui6.margin(gui6.Left, 10.0)
        if not inline:
            with gui6.Node():
                gui6.height(60)
        for i, port in enumerate(ports):
            with gui6.Node():
                gui6.flex_direction(gui6.Row)
                gui6.align_items(gui6.Center)
                components3.Label(text=names[i], color=(0,1,0,1), font_height=12)
                with GuiPort(name=port.uid, color=color_by_type(port.ty)):
                    gui6.width(32)
                    gui6.height(32)
                    gui6.margin(gui6.All, 10)

def plugin_template(template):
    iports = [port for port in template.desc.info['ports'] if port['type'].startswith('input')]
    oports = [port for port in template.desc.info['ports'] if port['type'].startswith('output')]
    with gui6.Node():
        gui6.flex_direction(gui6.Column)
        with gui6.Node():
            gui6.height(60)
            gui6.margin(gui6.Horizontal, 8.0)
            components3.Label(text=template.module, color=(1,1,1,1), font_height=16)
            components3.Label(text=template.label.decode('utf-8'), color=(1,1,1,1), font_height=24)
        with gui6.Node():
            gui6.flex_direction(gui6.Row)
            inport_column([p['name'].decode('utf-8') for p in iports], template.inputs, inline=True)
            outport_column([p['name'].decode('utf-8') for p in oports], template.outputs, inline=True)

class PipelineEditor(gui6.Node):
    def __init__(self, *args, pipeline, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        with gui6.NodeContextManager(self):
            gui6.flex_direction(gui6.Row)
            outport_column(pipeline.input_names, pipeline.inputs)
            for item in pipeline.pipe:
                if isinstance(item, Template):
                    plugin_template(item)
            inport_column(pipeline.output_names, pipeline.outputs)
        self.edges = {}
        for node in self.traverse():
            if isinstance(node, GuiPort) and isinstance(node.name, int):
                self.edges[node.name] = node, []
            if isinstance(node, GuiPort) and isinstance(node.value, int):
                self.edges[node.value][1].append(node)

    def pre_draw(self, ui, x, y):
        rect = self.rect.offset(x, y)
        gui6.trace(ui, (1,1,1,1), rect)
        line_width = ui.ctx.line_width
        ui.ctx.line_width = 10.0
        for src, dests in self.edges.values():
            gr = src.global_rect
            x = gr.hcenter
            y = gr.vcenter
            for dst in dests:
                gr1 = dst.global_rect
                x1 = gr1.hcenter
                y1 = gr1.vcenter
                program, vao, buffer, data = ui.mem(components3.line_draw_setup)
                program['scroll'] = 0,0
                program['size'] = ui.widget.width, ui.widget.height
                program['color'] = src.color
                data[0] = x
                data[1] = y
                data[2] = x1
                data[3] = y1
                buffer.write(data)
                vao.render(mode=ui.ctx.LINES)
        ui.ctx.line_width = line_width

class Blank(gui6.Node):
    def __init__(self, *args, width=0, **kwargs):
        super().__init__(*args, **kwargs)
        with gui6.NodeContextManager(self):
             gui6.width(width)

class PluginPager(gui6.Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with gui6.NodeContextManager(self):
            with gui6.Node(name="content"):
                gui6.flex_direction(gui6.Row)
                gui6.position_type(gui6.Relative)
                gui6.position(gui6.Left, 0.0)
        self.on_screen = 0
        self.add_10_on_screen()
        self.scroll_x = 0.0

    def update_after_scroll(self):
        content = self["content"]
        screen_width = gui6.YGNodeLayoutGetWidth(self.node)
        content_width = gui6.YGNodeLayoutGetWidth(content.node)
        self.hide_off_screen(screen_width)
        if self.on_screen >= len(selection):
            self.scroll_x = max(self.scroll_x, -(content_width - screen_width))
        self.scroll_x = min(0, self.scroll_x)
        if content_width + self.scroll_x < screen_width and self.on_screen < len(selection):
            self.add_10_on_screen()

    def hide_off_screen(self, screen_width):
        x0 = -self.scroll_x
        x1 = -self.scroll_x + screen_width
        for item in self["content"]:
            index = item.name
            hidden = isinstance(item, Blank)
            z0 = gui6.YGNodeLayoutGetLeft(item.node)
            z1 = z0 + gui6.YGNodeLayoutGetWidth(item.node)
            show = (max(x0,z0) <= min(x1,z1))
            if show and hidden:
                node = plugin_entry(*selection[index])
                node.name = index
                self["content"].swap_child(node, index)
            if not show and not hidden:
                self["content"].swap_child(Blank(name=index, width=z1-z0, _attach_=False), index)

    def add_10_on_screen(self):
        on_screen = self.on_screen
        for i, (root, name, desc) in enumerate(selection[on_screen:on_screen+10], on_screen):
            node = plugin_entry(root, name, desc)
            node.name = i
            self["content"].add_child(node)
        self.on_screen = min(on_screen + 10, len(selection))

    def re_present(self, start, stop):
        if self.start == start and self.stop == stop:
            return
        for item in list(self["content"]):
            if item.name < start:
                width = gui6.YGNodeLayoutGetWidth(item.node)
                self.scroll_x += width
            item.detach()
        for i, (root, name, desc) in enumerate(selection[start:stop], start):
            node = plugin_entry(root, name, desc)
            node.name = i
            self["content"].add_child(node)
        self.start = max(start, 0)
        self.stop = min(stop, len(selection))

    def post_draw(self, ui, x, y):
        if ui.inside:
            ui.hotitem = self
            if ui.activeitem is None and ui.buttons > 0:
                ui.activeitem = self
                ui.activestate = ui.mouse
        if ui.activeitem is self and ui.buttons > 0:
            px, py = ui.activestate
            mx, my = ui.mouse
            ui.activestate = ui.mouse
            content = self["content"].node
            self.scroll_x = self.scroll_x + (mx - px)
            self.update_after_scroll()
            gui6.YGNodeStyleSetPosition(content, gui6.Left, self.scroll_x)
        if ui.buttons == 0 and ui.hotitem == self and ui.activeitem == self:
            pass
            #content = self["content"].node
            #self.scroll_x -= 50
            #x = gui6.YGNodeStyleGetPosition(content, gui6.Left).value
            #gui6.YGNodeStyleSetPosition(content, gui6.Left, self.scroll_x)
            #self.update_after_scroll()
            #YGGetPosition(self.node, Left)
            #self.page += 5
            #self.present(self.page)

from visual.font import FontEngine

class KKnob(gui6.Node):
    def __init__(self, *args, info=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.info = info

    def pre_draw(self, ui, x, y):
      try:
        rect = self.rect.offset(x,y)
        port = self.info
        hint = port['hint']
        default = hint['default']
        if default is None:
            gui6.trace(ui, (1,0,0,1), rect)
        else:
            value = default['value']
            if hint['lower'] is None or hint['upper'] is None:
                gui6.trace(ui, (1,0,0,1), rect)
            else:
                gui6.circle_stroke(ui, (1,0,0,1), rect)
                lower = hint['lower'] or 0.0
                upper = hint['upper'] or 0.0
                if hint['sample_rate']:
                    lower *= 44100
                    upper *= 44100
                if default['ratio']:
                    u = value
                    if hint['logarithmic']:
                        if lower > 0 and upper > 0:
                            value = math.exp(math.log(lower) * u + math.log(upper) * (1-u))
                        else:
                            value = 0
                    else:
                        value = lower * u + upper * (1-u)
                else:
                    if hint['logarithmic']:
                        if lower > 0 and upper > 0:
                            u = math.log(value / upper) / math.log(lower / upper)
                        else:
                            u = 0
                    else:
                        u = (value - lower) / (upper - lower)
                x = rect.hcenter - math.sin(math.pi*(u * 1.5 + 0.25)) * rect.width/2
                y = rect.vcenter - math.cos(math.pi*(u * 1.5 + 0.25)) * rect.height/2
                gui6.circle_fill(ui, (1,1,1,1), (x-1,y-1,2,2))
            hc = rect.hcenter
            vc = rect.vcenter
            if hc != float('nan') and vc != float('nan'):
                text = "%.2f" % value
                font = ui.mem(FontEngine, int(12))
                width = font.measure(text)
                height = font.ascent + font.descent
                font.prepare((1,1,1,1))
                font.text(text, round(hc - width/2),
                                round(vc - height/2 + font.descent))
                font.finish()
      except ValueError:
        pass

@gui6.prefab(gui6.Node)
def plugin_entry(root, name, desc):
    name = name.decode('utf-8')
    with gui6.Node():
        gui6.padding(gui6.All, 10.0)
        with gui6.Node():
            gui6.flex_direction(gui6.Column)
            components3.Label(text=root, color=(1,1,1,1), font_height=16)
            components3.Label(text=name, color=(1,1,1,1), font_height=24)
            with gui6.Node():
                gui6.flex_direction(gui6.Row)
                inputs = [port for port in desc.info['ports'] if port['type'].startswith('input')]
                outputs = [port for port in desc.info['ports'] if port['type'].startswith('output')]
                with gui6.Node():
                    gui6.flex_direction(gui6.Column)
                    for i in inputs:
                        _name = i['name'].decode('utf-8')
                        if i['type'].endswith('*'):
                            _name += '*'
                        with gui6.Node():
                            gui6.flex_direction(gui6.Row)
                            gui6.align_items(gui6.Center)
                            with KKnob(info=i):
                                gui6.width(32)
                                gui6.height(32)
                                gui6.margin(gui6.All, 10)
                            components3.Label(text=_name, color=(1,0,1,1), font_height=12)
                with gui6.Node():
                    gui6.width(10)
                with gui6.Node():
                    gui6.flex_direction(gui6.Column)
                    gui6.align_items(gui6.FlexEnd)
                    for i in outputs:
                        _name = i['name'].decode('utf-8')
                        if i['type'].endswith('*'):
                            _name += '*'
                        with gui6.Node():
                            gui6.flex_direction(gui6.Row)
                            gui6.align_items(gui6.Center)
                            components3.Label(text=_name, color=(0,1,0,1), font_height=12)
                            with KKnob(info=i):
                                gui6.width(32)
                                gui6.height(32)
                                gui6.margin(gui6.All, 10)

@gui6.prefab(MainApp)
def main_widget(editor):
    gui6.flex_direction(gui6.Column)
    with PipelineEditor(pipeline=main_pipe):
        gui6.margin(gui6.All, 10.0)
        gui6.height(300.0)
        gui6.overflow(gui6.Scroll)
    # with PluginPager():
    #     gui6.padding(gui6.All, 10.0)
    #     gui6.flex_direction(gui6.Row)
    #     gui6.overflow(gui6.Scroll)

    # with components3.Border(color=(0,1,0,1)):
    #     gui6.width(100.0)
    #     gui6.height(100.0)
    # with components3.Border(color=(1,0,0,1)):
    #     gui6.width(100.0)
    #     gui6.height(100.0)
    # components3.Label(text="Hello world", color=(1,1,1,1))
    # components3.Label(text="Hello world", color=(1,1,1,1))
    # components3.Label(text="Hello world", color=(1,1,1,1))
    # components3.Label(text="Hello world", color=(1,1,1,1))
    # components3.Label(text="Hello world", color=(1,1,1,1))


    #with gui6.Node(layout=gui6.VBox(width=gui6.Flex(0), height=gui6.Flex(0))):
    #    with gui6.Node(layout=gui6.HBox(width=gui6.Flex(0), height=gui6.Flex(0))):
    #        with gui6.Node(layout=gui6.Padding(10, 10, 10, 10)):
    #            with components3.Border(layout=gui6.HBox(width=100, height=300), color=(1,0,0,1)):
    #                with gui6.Node(layout=gui6.VBox(width=gui6.Flex(0), height=gui6.Flex(0))):
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                with gui6.Node(layout=gui6.VBox(width=gui6.Flex(0), height=gui6.Flex(0))):
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #                    components3.Border(layout=gui6.Box(width=50, height=30), color=(0,1,0,1))
    #        with gui6.Node(layout=gui6.Padding(10, 10, 10, 10)):
    #            components3.Border(layout=gui6.Box(width=100, height=300), color=(1,0,0,1))
    #        with gui6.Node(layout=gui6.Padding(10, 10, 10, 10)):
    #            components3.Border(layout=gui6.Box(width=100, height=300), color=(1,0,0,1))
    #        with gui6.Node(layout=gui6.Padding(10, 10, 10, 10)):
    #            components3.Border(layout=gui6.Box(width=100, height=300), color=(1,0,0,1))
    #    with PluginPager(layout=gui6.HBox(align=gui6.align_high, width=gui6.Flex(0), height=gui6.Flex(0))):
    #        pass
    #                    #components3.Label(text=name, color=(1,1,1,1), font_height=24, layout=gui6.Box())
    #pass
    #v2.widget.Widget(layout=gui6.Box(width=gui6.Flex(0), height=gui6.Flex(0)))
    
    #components3.Fill(rect=gui6.Rect(10, 10, 50, 50), color=(0.5, 0.2, 0.4, 1.0))
    #components3.Border(rect=gui6.Rect(200, 10, 50, 50), color=(0.2, 0.8, 0.4, 1.0))
    #components3.Border(rect=gui6.Rect(200, 0, 50, 300), color=(0.2, 0.8, 0.4, 1.0))
    #with components3.Button(rect=gui6.Rect(200, 100, 50, 50)):
    #    components3.Label(layout=gui6.Box(absolute=(gui6.align_middle, gui6.align_middle)), text="button")

    #components3.Label(rect=gui6.Rect(200, 150, 50, 50), text="Hello world!")
    #with gui6.Node(layout=gui6.HBox(align=gui6.align_middle, width=gui6.Flex(0), height=gui6.Flex(0))):
    #    components3.Border(layout=gui6.Box(width=50, height=100), color=(0.5,0.5,0.5,1))
    #    with components3.Border(layout=gui6.VBox(width=gui6.Flex(0), height=0), color=(0.5,0.5,0.5,1)):
    #        with components3.Border(layout=gui6.Box(width=50, height=200), color=(1.0,0.5,0.5,1)):
    #            components3.Label(layout=gui6.Box(width=gui6.Flex(0), height=32), text="200")
    #        with components3.Border(layout=gui6.Box(width=50, height=300), color=(0.5,0.5,1.0,1)):
    #            components3.Label(layout=gui6.Box(width=gui6.Flex(0), height=32), text="300")
    #    with components3.Border(layout=gui6.VBox(width=gui6.Flex(0), height=gui6.Flex(0)), color=(0.5,0.5,0.5,1)):
    #        gui6.Node(layout=gui6.Box(width=0, height=gui6.Flex(0)))
    #        with components3.Border(layout=gui6.Box(width=50, height=200), color=(1.0,0.5,0.5,1)):
    #            components3.Label(layout=gui6.Box(), text="200")
    #        with components3.Border(layout=gui6.Box(width=50, height=300), color=(0.5,0.5,1.0,1)):
    #            components3.Label(layout=gui6.Box(), text="300")
    #        gui6.Node(layout=gui6.Box(width=0, height=gui6.Flex(0)))
    #        
    #    components3.Border(layout=gui6.Box(width=50, height=100), color=(0.5,0.5,0.5,1))

class Editor:
    def __init__(self):
        self.directory_contents = list(os.scandir("data/"))
        #self.thing = pd.DataFrame(
        #    data = { 'onset': pd.Series([0.1, 0.3], dtype='float32'),
        #             'offset': pd.Series([0.3, 0.6], dtype='float32'),
        #             'note': pd.Series([69, 80], dtype='uint16'),
        #             'velocity': pd.Series([1.0, 1.0], dtype='float32') },
        #    index = pd.Series([0,1], dtype='uint32'))

        locator = aural.ladspa.Locator()
        engine = aural.ladspa.Engine(sample_rate=44100, sample_count=2048)
        self.bay = bay = box.Bay(Engine(), engine, locator, pulse = Event())
        self.clavier = Source(bay.event_engine, as_stream)
        frame = Hold(0, bay.pulse)
        now = Compute(lambda frame: frame * engine.sample_step, [frame])

        ta = 1
        tih = 3 * ta / 4
        tempo = 90.0
        song1 = box.music(now, tempo, [
            (ta, {c4}),
            (ta, {e4, g4}),
            (ta, {e4, g4}),
        ], loop=True)
        song2 = box.music(now, tempo, [
            (tih, {f4}),
            (tih, {a4}),
            (tih, {b4}),
            (tih/2, {c5}),
            (tih/2, {e5}),
        ], loop=True)
        def merge_lists(x, y):
            match (x, y):
                case (Some(xs), Some(ys)):
                    return Some(xs+ys)
                case Some(xs):
                    return Some(xs)
                case Some(ys):
                    return Some(ys)
        song = Merge(song1, song2, merge_lists)

        # song = box.schedule(now, [
        #     (0.0,  On(52, 1.0)),
        #     (0.5,  Off(52)),
        #     (0.5,  On(59, 1.0)),
        #     (0.75, Off(59)),
        #     (0.75, On(54, 1.0)),
        #     (1.0,  Off(54)),
        # ], loop=1.0)

        #notes = Merge(self.clavier, song)
        notes = self.clavier

        def make_channel(bay, gate, trig, hz, velocity):
            modulator = box.sawtooth_fc(bay, Hold(100.0))
            hz  = Compute(lambda m, f: f / 4 + m*50.0, [modulator, hz])
            out = box.sawtooth_fa(bay, hz)
            env = box.adsr(bay, gate, trig, Hold(0.01), Hold(0.5), Hold(0.2), Hold(0.5))
            return Compute(lambda x, y: x * y, [out, env])

        def make_channel(bay, gate, trig, hz, velocity):
            modulator = box.sawtooth_fc(bay, Hold(800.0))
            hz  = Compute(lambda m, f: f / 2 + m*50.0, [modulator, hz])
            out = box.sawtooth_fa(bay, hz)
            env = box.adsr(bay, gate, trig, Hold(0.01), Hold(0.5), Hold(0.2), Hold(0.5))
            return Compute(lambda x, y: x * y, [out, env])

        # wobble = Compute(lambda now: 440.0 + math.sin(now * 2 * 1 * math.pi)*50.0, [now])
        # out = box.sin_fc_ac(bay, base_freq) 
        # out = box.sawtooth_fc(bay, base_freq) 

        #base_freq = box.as_frequency(69, notes)
        #out = box.monophonic(bay)(notes, make_channel)
        out = box.polyphonic(bay, now, voices=16)(notes, make_channel)
        #out = box.noise_white(bay, Hold(1.0))
        #out = Compute(lambda *xs: sum(xs), [out1, out2])

        lout = rout = out
        #out = box.tremolo(bay,
        #  frequency = Hold(100.0),
        #  depth_pc = Hold(60.0),
        #  gain = Hold(2.0),
        #  input = out)

        left  = engine.zeros()
        right = engine.zeros()
        @bay.event_engine.observe(lout, rout)
        def _listening_(ldata, rdata):
            left[:] = ldata
            right[:] = rdata
        self.audio_output = aural.device.SDLDevice(bay, left, right)
        self.out0 = engine.zeros()
        self.out1 = engine.zeros()

        self.running = False
        self.time = 0.0
        self.widgets = dict()

        mido_in = mido.backend.get_input_names()[-1]
        self.midi_input = mido.backend.open_input(mido_in)

        self.dataset = dict(
            count = set([(0,)]),
            note = set([(0,), (1,), (4,), (6,)]),
            bar  = set([(4,), (8,), (12,)]),
        )

    def fire_midi_keyboard(self, ui, m):
        ui.clavier.append(m)
        self.clavier.send(m)

    def widget(self, *args):
        widget = Widget(*args)
        self.widgets[widget.uid] = widget
        return widget

    def ui(self):
        self.running = True
        sdl2.ext.init(video=True, audio=True)

        flags = sdl2.SDL_WINDOW_RESIZABLE | sdl2.SDL_WINDOW_OPENGL
        root = self.widget("rollernote", 1200, 700, flags, gui6.GUI, main_widget(self))

        sdl2.SDL_StartTextInput()

        while self.running:
            self.time = sdl2.SDL_GetTicks64() / 1000.0
            self.running = process_widgets(self.widgets, root)
            self.audio_output.lock()

            real_events = []
            for msg in self.midi_input.iter_pending():
                if msg.type == 'note_on':
                    self.fire_midi_keyboard(root.payload, On(msg.note, msg.velocity / 127))
                if msg.type == 'note_off':
                    self.fire_midi_keyboard(root.payload, Off(msg.note))

            self.out0 = self.audio_output.channels[0][:]
            self.out1 = self.audio_output.channels[1][:]
            self.audio_output.unlock()

        self.audio_output.close()
        sdl2.SDL_StopTextInput()
        #self.pluginhost.close()
        sdl2.ext.quit()

if __name__=='__main__':
    Editor().ui()
