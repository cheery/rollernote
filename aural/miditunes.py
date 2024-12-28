notenames = {
    'ces': -1,
    'bis': 0, 'c': 0,
    'cis': 1, 'des': 1,
    'd': 2,
    'dis': 3, 'ees': 3,
    'e': 4, 'fes': 4,
    'eis': 5, 'f': 5,
    'fis': 6, 'ges': 6,
    'g': 7,
    'gis': 8, 'aes': 8,
    'a': 9,
    'ais': 10, 'bes': 10,
    'b': 11,
}

def make_notes():
    for name, offset in notenames.items():
        v = 12 + -1 * 12 + offset
        if 0 <= v <= 127:
            globals()[f"{name}n1"] = v
        for i in range(0, 10):
            v = 12 + i * 12 + offset
            if 0 <= v <= 127:
                globals()[f"{name}{i}"] = v
make_notes()
