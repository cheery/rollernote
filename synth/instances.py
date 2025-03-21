from .entities import signal, control
from .entities import Constant, Knob
from .entities import Template

def generate_type(engine, ty):
    if ty == signal:
        return engine.zeros()
    elif ty == control:
        return engine.cell(0.0)
    else:
        assert False, f"TODO: implement {ty.name}"

def build_pipeline(engine, locator, pipeline, inputs, cache):
    variables = {}
    for outport, data in zip(pipeline.inputs, inputs):
        variables[outport.uid] = data
    stages = []
    for stage in pipeline.pipe:
        if isinstance(stage, Template):
            inputs = iter(stage.inputs)
            outputs = iter(stage.outputs)
            plugin = cache.pop(stage.uid, None)
            if plugin is None:
                desc = locator.load(stage.module, stage.label)
                plugin = engine(desc)
                plugin.uid = stage.uid
            for i, port in enumerate(plugin.instance.desc.info['ports']):
                if port['type'].startswith('input'):
                    inport = next(inputs)
                    mk = engine.full if port['type'].endswith('*') else engine.cell
                    if isinstance(inport.value, int):
                        data = variables[inport.value]
                    elif isinstance(inport.value, Constant):
                        data = mk(inport.value.const)
                    elif isinstance(inport.value, Knob):
                        data = mk(inport.value.get_value())
                    else:
                        assert False, inport.value
                if port['type'].startswith('output'):
                    outport = next(outputs)
                    mk = engine.full if port['type'].endswith('*') else engine.cell
                    variables[outport.uid] = data = generate_type(engine, outport.ty)
                plugin.connect_port(i, data)
            stages.append(plugin)
        else:
            assert False, stage
    outputs = []
    for inport in pipeline.outputs:
        if isinstance(inport.value, int):
            data = variables[inport.value]
        else:
            if isinstance(inport.value, Constant):
                value = inport.value.const
            elif isinstance(inport.value, Knob):
                value = inport.value.get_value()
            if inport.ty == signal:
                data = engine.full(value)
            elif inport.ty == control:
                data = engine.cell(value)
            else:
                assert False, f"TODO: implement {ty.name}"
        outputs.append(data)
    for item in cache.values():
        item.close()
    return PipelineInstance(stages, outputs)

class PipelineInstance:
    def __init__(self, stages, outputs):
        self.stages = stages
        self.outputs = outputs

    def deconstruct(self):
        cache = {}
        for stage in self.stages:
            cache[stage.uid] = stage
        return cache

    def run(self):
        for stage in self.stages:
            stage.run()

class Transport:
    def __init__(self, engine, locator, pi):
        self.engine = engine
        self.locator = locator
        self.pi = pi

    def run(self):
        self.pi.run()

