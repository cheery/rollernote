from PIL import Image, ImageDraw, ImageFont
from . import atlas
from . import gui5
import numpy as np

class FontEngine:
    def __init__(self, ui, size):
        ui.mem(gui5.common_interface)
        self.ui = ui
        self.font = ImageFont.truetype('OpenSans-Regular.ttf', size=size)
        self.image = Image.new("L", (1024, 1024), color=0)
        self.draw = ImageDraw.Draw(self.image)
        self.atlas = atlas.AtlasAllocator(1024, 1024)
        self.mapping = dict()
        self.upload = False
        self.texture = ui.ctx.texture(self.image.size, 1)
        self.sampler = ui.ctx.sampler(texture=self.texture)
        self.sampler.filter = ui.ctx.NEAREST, ui.ctx.NEAREST

        self.ascent, self.descent = self.font.getmetrics()
        self.program = ui.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 xy;
                in vec4 xywh;
                out vec4 _xywh;
                void main() {
                    gl_Position = vec4(xy, 0.0, 1.0);
                    _xywh = xywh;
                }
            """,
            geometry_shader="""
                #version 330 core
                #include "common_ui"
                layout (points) in;
                layout (triangle_strip, max_vertices=4) out;
                in vec4 _xywh[];
                out vec2 uv;
                uniform vec2 uv_size;
                void main() {
                    vec2 position = gl_in[0].gl_Position.xy;
                    vec2 u0 = _xywh[0].xy / uv_size;
                    vec2 wh = _xywh[0].zw;
                    vec2 u1 = u0 + wh / uv_size;

                    gl_Position = vec4(pixel_to_screen(position + vec2(0, wh.y)), 0, 1);
                    uv = vec2(u0.x, u1.y);
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position + wh), 0, 1); 
                    uv = u1;
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position), 0, 1);
                    uv = u0;
                    EmitVertex();
                    gl_Position = vec4(pixel_to_screen(position + vec2(wh.x, 0)), 0, 1);
                    uv = vec2(u1.x, u0.y);
                    EmitVertex();
                    EndPrimitive();
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D sample;
                uniform vec4 color;
                in vec2 uv;
                out vec4 rgba;
                void main() {
                    rgba = color * vec4(1,1,1, texture(sample, uv).x);
                }
            """)
        self.vdata = np.full(6*4096, 0.0, dtype=np.float32)
        self.vcount = 0
        self.vbo = ui.ctx.buffer(self.vdata)
        self.vao = ui.ctx.vertex_array(self.program, self.vbo, 'xy', 'xywh')

    def inmap(self, ch):
        if ch not in self.mapping:
            (width, baseline), (offset_x, offset_y) = self.font.font.getsize(ch)
            mask = self.font.getmask(ch)
            bbox = mask.getbbox()
            if bbox is None:
                rect = None
                offset_y = 0
            else:
                mask = Image.frombytes(mask.mode, mask.size, bytes(mask))
                mask = mask.transpose(Image.FLIP_TOP_BOTTOM)
                ow, oh = mask.size
                ox, oy = self.atlas.alloc(ow, oh)
                self.draw.bitmap((ox, oy), mask, fill=255)
                self.upload = True
                rect = ox, oy, ow, oh
                offset_y = self.ascent - oh - offset_y
            self.mapping[ch] = (offset_x, offset_y), rect, width
        return self.mapping[ch]

    def measure(self, string):
        x = 0
        for ch in string:
            (offset_x, offset_y), rect, width = self.inmap(ch)
            x += width
        return x

    def prepare(self, color):
        self.program['scroll'] = self.ui.scroll_x, self.ui.scroll_y
        self.program['size'] = self.ui.widget.width, self.ui.widget.height
        self.program['uv_size'] = 1024, 1024
        self.program['color'] = color
        #self.program['sample'] = 0
        self.sampler.use(0)

    def text(self, string, x, y):
        for ch in string:
            (offset_x, offset_y), rect, width = self.inmap(ch)
            if rect is not None:
                ix = self.vcount*6
                self.vdata[ix+0] = x + offset_x
                self.vdata[ix+1] = y + offset_y
                self.vdata[ix+2:ix+6] = rect
                self.vcount += 1
                if self.vcount >= 4096:
                    self.finish()
            x += width

    def finish(self):
        if self.upload:
            self.texture.write(self.image.tobytes())
            self.upload = False
        self.vbo.write(self.vdata)
        self.vao.render(vertices=self.vcount, mode=self.ui.ctx.POINTS)
        self.vcount = 0

