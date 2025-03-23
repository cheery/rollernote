import math

class PrimType:
    pass

signal  = PrimType()
control = PrimType()
clavier = PrimType() # TODO: rename into something else

class Pipeline:
    def __init__(self, uid, name, inputs, pipe, outputs, input_names, output_names):
        self.uid = uid
        self.name = name
        self.inputs = inputs
        self.pipe = pipe
        self.outputs = outputs
        self.input_names = input_names
        self.output_names = output_names

class OutPort:
    def __init__(self, uid, ty):
        self.uid = uid
        self.ty  = ty

class InPort:
    def __init__(self, value, ty):
        self.value = value
        self.ty    = ty

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
            return math.exp(math.log(lower) * (1-u) + math.log(upper) * u)
        else:
            return lower * (1-u) + upper * u

def value_knob(lower, upper, value, is_log=False):
    if is_log:
        ratio = math.log(value / lower) / math.log(upper / lower)
    else:
        ratio = (value - lower) / (upper - lower)
    return Knob(lower, upper, ratio, is_log=is_log)

class Template:
    def __init__(self, uid, module, label, inputs, outputs):
        self.uid = uid
        self.module = module
        self.label = label
        self.inputs = inputs
        self.outputs = outputs
