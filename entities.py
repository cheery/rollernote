"""
    Document model
    Pitch representation
"""
from fractions import Fraction
import zipfile, json, io
import bisect
import random

class Document:
    def __init__(self, track, instruments, next_uid):
        self.track = track
        self.instruments = instruments
        self.next_uid = next_uid
        self.mutes = {}

    def init_plugins(self, pluginhost):
        plugins = {}
        for instrument in self.instruments:
            plugins[instrument.uid] = plugin = pluginhost.plugin(instrument.plugin)
            if len(instrument.patch) > 0:
                plugin.restore(instrument.patch, instrument.data)
        return plugins

    def store_plugins(self, plugins):
        for instrument in self.instruments:
            i = f"instrument.{instrument.uid}"
            instrument.patch, instrument.data = plugins[instrument.uid].store(i)

def load_document(filename):
    with zipfile.ZipFile(filename, 'r') as zf:
        with zf.open('document.json', 'r') as fd:
            document_json = json.load(io.TextIOWrapper(fd, 'utf-8'))
        with zf.open('track.json', 'r') as fd:
            track_json = json.load(io.TextIOWrapper(fd, 'utf-8'))
        instruments = []
        for uid in document_json['instrument_uids']:
            with zf.open(f'instrument.{uid}.json', 'r') as fd:
                instrument_json = json.load(io.TextIOWrapper(fd, 'utf-8'))
                instrument = Instrument.from_json(instrument_json, zf)
                instrument.uid = uid
            instruments.append(instrument)
    return Document(
        track = Track.from_json(track_json),
        instruments = instruments,
        next_uid = UidGenerator(document_json['next_uid']),
    )

def save_document(filename, document):
    with zipfile.ZipFile(filename, 'w') as zf:
        with zf.open('document.json', 'w') as fd:
            document_json = {
                'instrument_uids': [i.uid for i in document.instruments],
                'next_uid': document.next_uid.next_uid,
            }
            json.dump(
                document_json,
                io.TextIOWrapper(fd, 'utf-8'),
                sort_keys=True, indent=2)
        with zf.open('track.json', 'w') as fd:
            json.dump(
                document.track.as_json(),
                io.TextIOWrapper(fd, 'utf-8'),
                sort_keys=True, indent=2)
        for instrument in document.instruments:
            with zf.open(f'instrument.{instrument.uid}.json', 'w') as fd:
                json.dump(
                    instrument.as_json(),
                    io.TextIOWrapper(fd, 'utf-8'),
                    sort_keys=True, indent=2)
            for path, content in instrument.data.items():
                zf.writestr(path, content)

class Track:
    def __init__(self, graphs, voices):
        self.graphs = graphs
        self.voices = voices

    @staticmethod
    def from_json(record):
        return Track(
            graphs = [graph_from_json(a) for a in record['graphs']],
            voices = [Voice.from_json(a) for a in record['voices']],
        )

    def as_json(self):
        return {
            'graphs': [graph.as_json() for graph in self.graphs],
            'voices': [voice.as_json() for voice in self.voices]
        }

def graph_from_json(record):
    if record['type'] == 'staff':
        return Staff(
            uid = record['uid'],
            top = record['top'],
            bot = record['bot'],
            blocks = [StaffBlock.from_json(a) for a in record['blocks']],
        )
    elif record['type'] == 'chord_progression':
        return ChordProgression(
            uid = record['uid'],
            segments = [ChordProgressionSegment.from_json(a) for a in record['segments']],
        )
    elif record['type'] == 'envelope':
        return Envelope(
            uid = record['uid'],
            kind = record['kind'],
            segments = [EnvelopeSegment.from_json(a) for a in record['segments']],
        )
    else:
       raise ValueError

class ChordProgression:
    def __init__(self, uid, segments):
        self.uid = uid
        self.segments = segments

    def as_json(self):
        return {
            'type': 'chord_progression',
            'uid': self.uid,
            'segments': [seg.as_json() for seg in self.segments],
        }

class ChordProgressionSegment:
    def __init__(self, nth, duration):
        self.nth = nth
        self.duration = duration

    @staticmethod
    def from_json(record):
        numerator, denominator = record['duration']
        return ChordProgressionSegment(
            nth = record['nth'],
            duration = Fraction(numerator, denominator),
        )

    def as_json(self):
        return {
            'nth': self.nth,
            'duration': self.duration.as_integer_ratio()
        }

class Envelope:
    def __init__(self, uid, kind, segments):
        self.uid = uid
        self.kind = kind
        self.segments = segments

    def as_json(self):
        return {
            'type': 'envelope',
            'uid': self.uid,
            'kind': self.kind,
            'segments': [seg.as_json() for seg in self.segments],
        }

class EnvelopeSegment:
    def __init__(self, control, value, duration):
        self.control = control
        self.value = value
        self.duration = duration

    @staticmethod
    def from_json(record):
        numerator, denominator = record['duration']
        return EnvelopeSegment(
            control = record['control'],
            value = record['value'],
            duration = Fraction(numerator, denominator),
        )

    def as_json(self):
        return {
            'control': self.control,
            'value': self.value,
            'duration': self.duration.as_integer_ratio()
        }

class Staff:
    def __init__(self, uid, top, bot, blocks):
        self.uid = uid
        self.top = top
        self.bot = bot
        self.blocks = blocks

    def as_json(self):
        return {
            'type': "staff",
            'uid': self.uid,
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

class Voice:
    def __init__(self, uid, staff_uid, dynamics_uid, segments):
        self.uid = uid
        self.staff_uid = staff_uid
        self.dynamics_uid = dynamics_uid
        self.segments = segments

    @staticmethod
    def from_json(record):
        return Voice(
            uid = record['uid'],
            staff_uid = record['staff_uid'],
            dynamics_uid = record.get('dynamics_uid'), # TODO: change later
            segments = [VoiceSegment.from_json(a) for a in record['segments']],
        )

    def as_json(self):
        return {
            'uid': self.uid,
            'staff_uid': self.staff_uid,
            'dynamics_uid': self.dynamics_uid,
            'segments': [seg.as_json() for seg in self.segments],
        }

class VoiceSegment:
    def __init__(self, notes, duration):
        self.notes = notes
        self.duration = duration # In beats

    @staticmethod
    def from_json(record):
        numerator, denominator = record['duration']
        return VoiceSegment(
            notes = [Note.from_json(note) for note in record['notes']],
            duration = Fraction(numerator, denominator)
        )

    def as_json(self):
        return {
            'duration': self.duration.as_integer_ratio(),
            'notes': [note.to_json() for note in self.notes]
        }

class Instrument:
    def __init__(self, plugin, patch, data, uid):
        self.plugin = plugin
        self.patch = patch
        self.data = data
        self.uid = uid

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
            uid = record['uid'],
        )

    def as_json(self):
        return {
            'plugin': self.plugin,
            'patch': self.patch,
            'uid': self.uid,
        }

class Note:
    def __init__(self, pitch, instrument_uid):
        self.pitch = pitch
        self.instrument_uid = instrument_uid

    @staticmethod
    def from_json(record):
        position, accidental = record['pitch']
        return Note(
            pitch = Pitch(position, accidental),
            instrument_uid = record['instrument_uid'],
        )
        
    def to_json(self):
        return {
            'pitch': self.pitch.to_pair(),
            'instrument_uid': self.instrument_uid,
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

class UidGenerator:
    def __init__(self, next_uid):
        self.next_uid = next_uid

    def __call__(self):
        uid = self.next_uid
        self.next_uid += random.randint(1, 100)
        return uid
