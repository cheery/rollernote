"""
    Primitive objects for gui building.
"""
import math

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
