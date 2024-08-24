from fractions import Fraction
import entities

char_accidental = {
    2: chr(119083),
   -1: chr(0x266d),
    0: chr(0x266e),
   +1: chr(0x266f),
   +2: chr(119082),
}

# order of sharps in a canonical key
         #F C G D A E B
sharps = [3,0,4,1,5,2,6]

def canon_key(index):
    key = list(base_key)
    for i in range(0, index):
        key[sharps[i]] += 1
    for i in range(index, 0):
        key[sharps[i]] -= 1
    return key

# index = 0 for major
# index = 5 for minor
def tonic(canonical_key, index=0):
    nkey = [i % 12 for i in canon_key(canonical_key)]
    k = base_key[index]
    return entities.Pitch(nkey.index((canonical_key * 7 + k) % 12))

# The pitch representation is contextual,
# next function converts the pitch to canonical representation.

base_key = [0,2,4,5,7,9,11]
def resolve_pitch(note, key=base_key):
    octave = note.position // 7
    if note.accidental is None:
        pc = key[note.position % 7]
        return (octave+1)*12 + pc
    else:
        pc = base_key[note.position % 7]
        return (octave+1)*12 + pc + note.accidental

def pitch_name(p, key=base_key, show_octave=True):
    if isinstance(p, entities.Pitch):
        q = resolve_pitch(p, key)
        p = resolve_pitch(p)
    else:
        q = p
    letter = "CCDDEFFGGAAB"[p%12]
    if q == p:
        accidental = " # #  # # # "[p%12].strip()
    else:
        accidental = char_accidental[q-p]
    octave = p//12 - 1
    return letter + accidental + str(octave)*show_octave

# The canonical pitch can be converted to its enharmonics.
def enharmonics(pitch, key=base_key):
    octave = (pitch // 12)-1
    pc = pitch % 12
    try:
        i = list(x % 12 for x in key).index(pc)
        yield entities.Pitch(octave * (7 + (key[i] // 12)) + i)
    except ValueError:
        pass
    for k in range(-2, 3):
        octave = ((pitch - k) // 12)-1
        pc = (pitch - k) % 12
        try:
            yield entities.Pitch(octave * 7 + base_key.index(pc), k)
        except ValueError:
            pass


# Convert canonically represented chord to notated form,
# such that no note intersects an another.
def chord_enharmonics(canonical_pitches):
    Y = {}
    positions = set()
    for pitch in canonical_pitches:
        for n in enharmonics(pitch):
            insert_in_list(Y, n, ('canon', pitch))
            insert_in_list(Y, n, ('staff', n.position))
            positions.add(n.position)
    for position in positions:
        insert_in_list(Y, position, ('staff', position))
    # The problem is solved as an exact cover problem.
    X = build_X(Y)
    for solution in solve(X, Y, []):
        yield list(s for s in solution if isinstance(s, entities.Pitch))

def build_X(Y):
    X = dict()
    for key, values in Y.items():
        for val in values:
            insert_in_set(X, val, key)
    return X

def insert_in_list(group, key, val):
    try:
        group[key].append(val)
    except KeyError:
        group[key] = [val]

def insert_in_set(group, key, val):
    try:
        group[key].add(val)
    except KeyError:
        group[key] = set([val])

# https://www.cs.mcgill.ca/~aassaf9/python/algorithm_x.html
def solve(X, Y, solution):
    if not X:
        yield list(solution)
    else:
        c = min(X, key=lambda c: len(X[c]))
        for r in list(X[c]):
            solution.append(r)
            cols = select(X, Y, r)
            for s in solve(X, Y, solution):
                yield s
            deselect(X, Y, r, cols)
            solution.pop()

def select(X, Y, r):
    cols = []
    for j in Y[r]:
        for i in X[j]:
            for k in Y[i]:
                if k != j:
                    X[k].remove(i)
        cols.append(X.pop(j))
    return cols

def deselect(X, Y, r, cols):
    for j in reversed(Y[r]):
        X[j] = cols.pop()
        for i in X[j]:
            for k in Y[i]:
                if k != j:
                    X[k].add(i)

def pitch_complexity(pitch):
    if pitch.accidental is None:
        return 0
    else:
        return 1 + abs(pitch.accidental)

def categorize_note_duration(fraction):
    for i in range(10):
        base_note = Fraction(4) / (2**i)
        if fraction == base_note * 2 / 3:
            return base_note, 0, True
        if fraction == base_note:
            return base_note, 0, False
        total = base_note
        for n in range(0, 4):
            total += base_note / (2**(n+1))
            if fraction == total:
                return base_note, n+1, False

def generate_all_note_durations():
    for i in range(10):
        base_note = Fraction(4) / (2**i)
        yield base_note
        yield base_note * 2 / 3
        total = base_note
        for n in range(0, 4):
            total += base_note / (2**(n+1))
            yield total

def quantize_fraction(input_value):
    rounded = round(input_value)
    fraction = min(generate_all_note_durations(), key=lambda note: abs(input_value - float(note)))
    # Aside musical fractions, we also want to quantize to beat boundaries.
    # This is important because the cutting/joining tools quantize
    if rounded > 0 and abs(input_value - rounded) < abs(input_value - float(fraction)):
        return Fraction(rounded)
    else:
        return fraction
