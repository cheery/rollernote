"""
    Document model
    Pitch representation
"""
from fractions import Fraction
import zipfile, json, io

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
    def __init__(self, voices):
        self.voices = voices

    @staticmethod
    def from_json(record):
        return Track(
            voices = [[VoiceSegment.from_json(vs) for vs in voice]
                      for voice in record['voices']]
        )

    def as_json(self):
        return {
            'voices': [[vs.as_json() for vs in voice] for voice in self.voices]
        }

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
