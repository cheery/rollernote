"""
    Document model
    Pitch representation
"""
from fractions import Fraction
import zipfile, json, io
import bisect

class Document:
    def __init__(self, track, instrument):
        self.track = track
        self.instrument = instrument

def load_document(filename):
    with zipfile.ZipFile(filename, 'r') as zf:
        with zf.open('track.json', 'r') as fd:
            track_json = json.load(io.TextIOWrapper(fd, 'utf-8'))
        with zf.open('instrument.json', 'r') as fd:
            instrument_json = json.load(io.TextIOWrapper(fd, 'utf-8'))
            instrument = Instrument.from_json(instrument_json, zf)
    return Document(
        track = Track.from_json(track_json),
        instrument = instrument,
    )

def save_document(filename, document):
    with zipfile.ZipFile(filename, 'w') as zf:
        with zf.open('track.json', 'w') as fd:
            json.dump(
                document.track.as_json(),
                io.TextIOWrapper(fd, 'utf-8'),
                sort_keys=True, indent=2)
        with zf.open('instrument.json', 'w') as fd:
            json.dump(
                document.instrument.as_json(),
                io.TextIOWrapper(fd, 'utf-8'),
                sort_keys=True, indent=2)
        for path, content in document.instrument.data.items():
            zf.writestr(path, content)

class Track:
    def __init__(self, graphs, voices):
        self.graphs = graphs
        self.voices = voices

    @staticmethod
    def from_json(record):
        return Track(
            graphs = [graph_from_json(a) for a in record['graphs']],
            voices = [[VoiceSegment.from_json(vs) for vs in voice]
                      for voice in record['voices']]
        )

    def as_json(self):
        return {
            'graphs': [graph.as_json() for graph in self.graphs],
            'voices': [[vs.as_json() for vs in voice] for voice in self.voices]
        }

def graph_from_json(record):
    if record['type'] == 'staff':
        return Staff(
            top = record['top'],
            bot = record['bot'],
            blocks = [StaffBlock.from_json(a) for a in record['blocks']],
        )
    else:
       raise ValueError

class Staff:
    def __init__(self, top, bot, blocks):
        self.top = top
        self.bot = bot
        self.blocks = blocks

    def as_json(self):
        return {
            'type': "staff",
            'top': self.top,
            'bot': self.bot,
            'blocks': [block.as_json() for block in self.blocks],
        }

# Staff is required to have at least one at beat=0, with all parameters present.
# In later blocks the parameters may fill up from the previous blocks.
class StaffBlock:
    def __init__(self, beat, beats_in_measure=None, beat_unit=None, canonical_key=None, clef=None, mode=None):
        self.beat = beat
        self.beats_in_measure = beats_in_measure
        self.beat_unit = beat_unit
        self.canonical_key = canonical_key # Between -7, +7
        self.clef = clef # a numerical value describing how the pitches are positioned on the staff.
        self.mode = mode # None, 'major' or 'minor'

    def complete_from(self, source):
        opt = lambda x, default: default if x is None else x
        return StaffBlock(self.beat,
            opt(self.beats_in_measure, source.beats_in_measure),
            opt(self.beat_unit, source.beat_unit),
            opt(self.canonical_key, source.canonical_key),
            opt(self.clef, source.clef),
            opt(self.mode, source.mode)
        )

    @staticmethod
    def from_json(record):
        return StaffBlock(
            beat = record['beat'],
            beats_in_measure = record['beats_in_measure'],
            beat_unit = record['beat_unit'],
            canonical_key = record['canonical_key'],
            clef = record['clef'],
            mode = record['mode'],
        )

    def as_json(self):
        return {
            'beat': self.beat,
            'beats_in_measure': self.beats_in_measure,
            'beat_unit': self.beat_unit,
            'canonical_key': self.canonical_key,
            'clef': self.clef,
            'mode': self.mode,
        }

def smear(staff_blocks):
    blocks = []
    current = staff_blocks[0]
    for block in staff_blocks[1:]:
        blocks.append(current)
        current = block.complete_from(current)
    blocks.append(current)
    return blocks

def by_beat(blocks, beat):
    return blocks[bisect.bisect(blocks, beat, key=lambda p: p.beat) - 1]

def at_beat(blocks, beat):
    i = bisect.bisect(blocks, beat, key=lambda p: p.beat)
    if i < len(blocks):
        return blocks[i-1], blocks[i]
    else:
        return blocks[i-1], None

class VoiceSegment:
    def __init__(self, notes, duration):
        self.notes = notes
        self.duration = duration # In beats

    @staticmethod
    def from_json(record):
        numerator, denominator = record['duration']
        def note_from_json(note):
            position, accidental = note['pitch']
            return Pitch(position, accidental)
        return VoiceSegment(
            notes = [note_from_json(note) for note in record['notes']],
            duration = Fraction(numerator, denominator)
        )

    def as_json(self):
        return {
            'duration': self.duration.as_integer_ratio(),
            'notes': [
               {
                   'pitch': note.to_pair()
               }
               for note in self.notes]
        }

class Instrument:
    def __init__(self, plugin, patch, data):
        self.plugin = plugin
        self.patch = patch
        self.data = data

    @staticmethod
    def from_json(record, zf):
        patch = record['patch']
        data = {}
        for row in patch.values():
            data[ row['path'] ] = zf.read(row['path'])
        return Instrument(
            plugin = record['plugin'],
            patch = patch,
            data = data,
        )

    def as_json(self):
        return {
            'plugin': self.plugin,
            'patch': self.patch,
        }

class Pitch:
    def __init__(self, position, accidental=None):
        self.position = position
        self.accidental = accidental

    def __repr__(self):
        a = "p"
        if self.accidental is not None:
            a = ['bb', 'b', 'n', 's', 'ss'][self.accidental+2]
        return f"{a}{self.position}"

    def to_pair(self):
        return self.position, self.accidental

    def __eq__(self, other):
        return self.to_pair() == other.to_pair()

    def __hash__(self):
        return hash(self.to_pair())
