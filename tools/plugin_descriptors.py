from aural import ladspa

locator = ladspa.Locator()
for root, label, desc in locator.list():
    model = repr((root, label))
    inputs = []
    outputs = []
    sr = False
    for port in desc.info['ports']:
        if port['type'].startswith('input'):
            inputs.append(port['name'])
    for port in desc.info['ports']:
        if port['hint']['sample_rate']:
            sr = True
            print(f"""# SR {port['name']}""")
        if port['type'].startswith('output'):
            outputs.append(port['name'])
    py_names = ['_' for _ in inputs]

    if sr:
        print(model)
    # print(f"""_ = PluginTemplate(
    # model = {model},
    # inputs = {inputs},
    # py_names = {py_names},
    # outputs = {outputs})
    # """)
