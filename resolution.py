from fractions import Fraction
import entities
import colorsys
import bisect
import math

char_accidental = {
   -2: chr(119083),
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
    return nkey.index((canonical_key * 7 + k) % 12)

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
def chord_enharmonics(canonical_pitches, key=base_key):
    Y = {}
    positions = set()
    for pitch in canonical_pitches:
        for n in enharmonics(pitch, key):
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

#def categorize_note_duration(fraction):
#    for i in range(10):
#        base_note = Fraction(4) / (2**i)
#        if fraction == base_note * 2 / 3:
#            return base_note, 0, True
#        if fraction == base_note:
#            return base_note, 0, False
#        total = base_note
#        for n in range(0, 4):
#            total += base_note / (2**(n+1))
#            if fraction == total:
#                return base_note, n+1, False
#
#def build_note_duration(base_note, dots, tri):
#    if tri:
#        return base_note * 2 / 3
#    total = base_note
#    for n in range(0, dots):
#        total += base_note / (2**(n+1))
#    return total
#
#def generate_all_note_durations():
#    for i in range(10):
#        base_note = Fraction(4) / (2**i)
#        yield base_note
#        yield base_note * 2 / 3
#        total = base_note
#        for n in range(0, 4):
#            total += base_note / (2**(n+1))
#            yield total

#def quantize_fraction(input_value):
#    rounded = round(input_value)
#    fraction = min(generate_all_note_durations(), key=lambda note: abs(input_value - float(note)))
#    # Aside musical fractions, we also want to quantize to beat boundaries.
#    # This is important because the cutting/joining tools quantize
#    if rounded > 0 and abs(input_value - rounded) < abs(input_value - float(fraction)):
#        return Fraction(rounded)
#    else:
#        return fraction

def find_next_value(index, segments):
    """Find the next defined value"""
    for i in range(index + 1, len(segments)):
        if segments[i].control != 0:
            return None
        if segments[i].value is not None:
            return segments[i].value
    return None

def linear_envelope(segments, default):
    current_value = default
    current_position = 0.0
    envelope = []

    if len(segments) == 0:
        envelope.append((current_position, current_value, 0))

    # Traverse segments
    for i, segment in enumerate(segments):
        duration = segment.duration
    
        if segment.control == 0 and segment.value is None:
            envelope.append((current_position, current_value, 0))
        elif segment.control == 0:
            # Immediate value change
            value = segment.value
            envelope.append((current_position, value, 0))
            current_value = value
        else:
            next_value = find_next_value(i, segments)
            if segment.control > 0 and next_value <= current_value:
                next_value = None
            if segment.control < 0 and next_value >= current_value:
                next_value = None
            if next_value is not None:
                end_value = next_value
            else:
                # Assume 10% above/below the current value
                end_value = current_value * (1.0 + 0.1 * segment.control)
            start_value = current_value
            slope = (end_value - start_value) / float(duration)
            envelope.append((current_position, start_value, slope))
            current_value = end_value
    
        # Move to the next position
        current_position += float(duration)
    return LinearEnvelope(envelope)

class LinearEnvelope:
    def __init__(self, vector):
        self.vector = vector # vector consists of list of triples:
                             # position, constant, change rate
        self.time_segments = None

    def value(self, position):
        i = bisect.bisect_right(self.vector, position, key=lambda v: v[0]) - 1
        p, c, k = self.vector[i]
        return (position - p)*k + c

    def area(self, position, duration, f=lambda x: x):
        i = 0
        for j, (p, k0, k1) in enumerate(self.vector):
            if p <= position:
                i = j
        endpoint = position + duration
        accum = 0
        while i < len(self.vector) and self.vector[i][0] < endpoint:
            p, k0, k1 = self.vector[i]
            q = self.vector[i+1][0] if i+1 < len(self.vector) else endpoint
            x0 = max(p, position)
            x1 = min(q, endpoint)
            y0 = x0*k1 + k0
            y1 = x1*k1 + k0
            accum += (x1-x0)*f((y0+y1)/2)
            i += 1
        return accum

    def check_positiveness(self, allow_zero = False):
        p, k0, k1 = self.vector[0]
        positive = (p * k1 + k0)
        
        for i, (p, h0, h1) in enumerate(self.vector):
            if i > 0:
                q, k0, k1 = self.vector[i-1]
                y = (p-q)*k1 + k0
                positive = min(positive, y)
        p, k0, k1 = self.vector[-1]
        if k0 > 0 and k1 >= 0:
            if allow_zero:
                return positive >= 0
            else:
                return positive > 0
        else:
            return False

    def _time_segments(self):
        time = 0.0
        for i, (p, c, k) in enumerate(self.vector):
            yield time
            if i+1 < len(self.vector):
                q = self.vector[i+1][0]
                if k == 0:
                    time += (q - p) * 60 / c
                else:
                    time += 60 / k * math.log((k * (q - p) + c) / c)

    def beat_to_time(self, beat):
        if self.time_segments is None:
            self.time_segments = list(self._time_segments())
        i = bisect.bisect_right(self.vector, beat, key=lambda v: v[0]) - 1
        time = self.time_segments[i]
        p, c, k = self.vector[i]
        if k == 0:
            return time + (beat - p) * 60 / c
        else:
            return time + 60 / k * math.log((k * (beat - p) + c) / c)

    def time_to_beat(self, time):
        if self.time_segments is None:
            self.time_segments = list(self._time_segments())
        i = bisect.bisect_right(self.time_segments, time) - 1
        t0 = self.time_segments[i]
        p, c, k = self.vector[i]
        if k == 0:
            return p + (time - t0)*c / 60
        else:
            return p + c * (math.exp(k*(time - t0) / 60) - 1) / k

#                                        1.0            0.5
def golden_ratio_color(index, saturation=0.7, lightness=0.5, alpha=1.0):
    """
    Generate an approximately evenly distributed color based on the index.

    Parameters:
    - index: int, the index of the color to generate.
    - saturation: float, the saturation of the color (0.0 to 1.0, default is 0.7).
    - lightness: float, the lightness of the color (0.0 to 1.0, default is 0.5).
    - alpha: float, the alpha transparency of the color (0.0 to 1.0, default is 1.0).

    Returns:
    - tuple (r, g, b, a): The color in (R, G, B, A) format.
    """
    golden_ratio_conjugate = 0.61803398875
    hue = (index * golden_ratio_conjugate) % 1.0
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (r, g, b, alpha)

def golden_ratio_color_varying(index, alpha=1.0):
    """
    Generate an approximately evenly distributed color with varying lightness and saturation based on the index.

    Parameters:
    - index: int, the index of the color to generate.
    - alpha: float, the alpha transparency of the color (0.0 to 1.0, default is 1.0).

    Returns:
    - tuple (r, g, b, a): The color in (R, G, B, A) format.
    """
    golden_ratio_conjugate = 0.61803398875
    hue = (index * golden_ratio_conjugate) % 1.0
    
    # Vary saturation and lightness slightly based on index
    lightness = 0.55 - 0.2 * ((index % 5) - 2) / 4.0
    # Saturation varies between 0.6 and 0.8
    saturation = 1.0 - 0.3 * ((index % 3) - 1) / 2.0
    
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (r, g, b, alpha)

def sequence_interpolation(value, sequence, interpolant, use_highest=False):
    li = bisect.bisect_left(sequence, value)
    ri = bisect.bisect_right(sequence, value)
    if li < len(sequence) and sequence[li] == value:
        if use_highest:
            return interpolant[ri-1]
        else:
            return interpolant[li]
    lowi = max(0, li - 1)
    uppi = min(len(sequence) - 1, ri)
    if sequence[uppi] != sequence[lowi]:
        t = (value - sequence[lowi]) / (sequence[uppi] - sequence[lowi])
    else:
        t = 0
    return interpolant[lowi]*(1-t) + interpolant[uppi]*t

def mean(xs, default=None):
    xs = list(xs)
    if len(xs) == 0:
        if default is None:
            raise ValueError
        else:
            return default
    return sum(xs) // len(xs)

def frange(start, stop, step, inclusive=False):
    current = start
    while current < stop:
        yield current
        current += step
    if inclusive and current <= stop:
        yield current

def base_note(n):
    if n < 0:
        return Fraction(1, 2**(-n))
    else:
        return Fraction(2**n)

def dotted_note(n, d):
    return (2 ** (d + 1) - 1) * base_note(n-d)

def fragmented_note(n, d):
    return base_note(n) / d

def as_fragment(x):
    n, d = x.as_integer_ratio()
    a = 0
    while n & 1 == 0 and d & 1 == 0:
        n >>= 1
        d >>= 1
    while n & 1 == 0:
        n >>= 1
        a += 1
    while d & 1 == 0:
        d >>= 1
        a -= 1
    return a, Fraction(d, n)

def categorize_duration(duration, limits, primes=(3,5,7,11)):
    above = lambda x: limits is None or limits[0] <= x
    below = lambda x: limits is None or x <= limits[1]
    less  = lambda x: limits is None or x <= limits[2]
    n, k = as_fragment(duration)
    if k.numerator == 1:
        dots = -1
        c = k.denominator + 1
        while c & 1 == 0:
            c >>= 1
            dots += 1
        if c == 1 and above(n+dots) and below(n+dots) and less(dots):
            return 'dotted', n+dots, dots # Detected dotted or bare note
    while not above(n):
        n += 1
        k *= 2
    while not below(n):
        n -= 1
        k /= 2
    if k.numerator == 1:
        return 'repeated', n, k.denominator # Detected repeated base notes
    elif k.denominator == 1 and k.numerator in primes: 
        return 'fragment', n, k.numerator # Detected fragment of a tuplet.
    else:
        return 'arbitrary', n, k # Detected arbitrary note

def rebuild_duration(category, n, k):
    if category == 'dotted':
        return dotted_note(n, k)
    elif category == 'repeated':
        return base_note(n) * k
    elif category == 'fragment' or category == 'arbitrary':
        return base_note(n) / k

def valid_durations(limits, extra=(), primes=(3,5,7,11)):
    for duration in extra:
        yield duration
    for n in range(limits[0], limits[1]+1):
        for k in range(limits[2]+1):
            yield dotted_note(n, k)
        for k in primes:
            yield base_note(n) / k

def quantize(value, beat_unit, limits, primes=(3,5,7,11)):
    distance_function = lambda x: abs(float(x) - value / beat_unit)
    repeated = Fraction(round(value)) / beat_unit
    if repeated == 0:
        repeated += Fraction(1, beat_unit)
    return min(valid_durations(limits, [repeated], primes),
               key=distance_function) * beat_unit

def quantize_and_categorize(value, beat_unit, limits, primes=(3,5,7,11)):
    closest = quantize(value, beat_unit, limits, primes)
    return categorize_duration(closest / beat_unit, limits)

def flexible_categorize(value, beat_unit, limits, primes=(3,5,7,11)):
    category, n, k = categorize_duration(value / beat_unit, limits)
    if category != 'arbitrary':
        return category, n, k, False
    category, n, k = quantize_and_categorize(float(value), beat_unit, limits, primes)
    return category, n, k, True

# This is not used for anything, but it might become useful later.
def closest_fraction(value, n, m): # Using Farey sequence
    a_num = 0
    a_denom = 1

    b_num = math.ceil(value)
    b_denom = 1

    c_num   = a_num   + b_num
    c_denom = a_denom + b_denom
    while not (c_num > n or c_denom > m):
        if c_num/c_denom < value:
            a_num = c_num
            a_denom = c_denom
        else:
            b_num = c_num
            b_denom = c_denom
        c_num   = a_num   + b_num
        c_denom = a_denom + b_denom

    if value - a_num/a_denom < b_num/b_denom - value:
        return Fraction(a_num, a_denom)
    else:
        return Fraction(b_num, b_denom)

    # Convert floating-point value to a Fraction
    frac = Fraction.from_float(value)
    return frac
