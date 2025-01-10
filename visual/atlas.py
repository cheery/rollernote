from collections import namedtuple

Strip = namedtuple('Strip', ['x', 'y0', 'y1', 'max_height'])

def reserve(strip, width, height):
    x0, y0, y1, max_height = strip
    x1 = x0 + width
    y1 = max(y0 + height, y1)
    return x0, y0, Strip(x1, y0, y1, max_height)
    
def compact(strip):
    x0, y0, y1, _ = strip
    return Strip(x0, y0, y1, max_height=y1 - y0)

class AtlasAllocator:
    __slots__ = ['width', 'height', 'strips']
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.strips = [Strip(0, 0, 0, height)]

    def alloc(self, width, height):
        for i, strip in enumerate(self.strips):
            if self.width - strip.x >= width and strip.max_height >= height:
                x, y, self.strips[i] = reserve(strip, width, height)
                return (x, y)
        if self.width >= width and self.height - strip.y1 >= height:
            self.strips[i] = strip = compact(strip)
            new = Strip(0, strip.y1, strip.y1, max_height=self.height - strip.y1)
            x, y, new = reserve(new, width, height)
            self.strips.append(new)
            return (x, y)
