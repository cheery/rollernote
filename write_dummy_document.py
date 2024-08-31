from fractions import Fraction
from entities import *

document = Document(
  next_uid = UidGenerator(1500),
  track = Track(
    graphs = [
      Staff(100, 3, 2, [
        StaffBlock(
          beat = 0,
          beats_in_measure = 4,
          beat_unit = 4,
          canonical_key = 7, # F#
          clef = -3, # Alto clef
          mode = None,
        ),
        StaffBlock(
          beat = 7,
          beats_in_measure = 3,
          canonical_key = +2, # D
          mode = 'major',
          clef = 3, # Treble/bass clef
        ),
      ]),
      Staff(200, 3, 2, [
        StaffBlock(
          beat = 0,
          beats_in_measure = 3,
          beat_unit = 4,
          canonical_key = 0, # C
          clef = 3, # Treble clef
          mode = None,
        ),
        StaffBlock(
          beat = 7,
          beats_in_measure = 3,
          canonical_key = +2, # D
        ),
      ]),
    ],
    voices = [
      Voice(300, 100, None, [
        VoiceSegment([Note(Pitch(32, +1), 600)], Fraction(4)),
        VoiceSegment([Note(Pitch(32), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(32), 600)], Fraction(1)),
        VoiceSegment([Note(Pitch(32), 600)], Fraction(1)),
        VoiceSegment([Note(Pitch(36), 600)], Fraction(1)),
        VoiceSegment([Note(Pitch(38), 600)], Fraction(1)),
        VoiceSegment([Note(Pitch(40), 600)], Fraction(1, 2)),
        VoiceSegment([],         Fraction(1, 2)),
        VoiceSegment([Note(Pitch(34, -1), 600)], Fraction(1)),
        VoiceSegment([Note(Pitch(35), 600)], Fraction(1, 2)),
        VoiceSegment([Note(Pitch(36), 600)], Fraction(1, 4)),
        VoiceSegment([Note(Pitch(37), 600)], Fraction(1, 8)),
        VoiceSegment([Note(Pitch(37), 600)], Fraction(1, 16)),
        VoiceSegment([Note(Pitch(37), 600), Note(Pitch(30), 600)], Fraction(3, 16)),
        VoiceSegment([Note(Pitch(37), 600)], Fraction(1, 4) + Fraction(1, 8) + Fraction(1, 16)),
        VoiceSegment([Note(Pitch(37), 600)], Fraction(1, 3)),
      ]),
      Voice(400, 100, None, [
        VoiceSegment([Note(Pitch(24), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(25), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(26), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(27), 600)], Fraction(2)),
      ]),
      Voice(500, 200, None, [
        VoiceSegment([Note(Pitch(24), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(25), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(26), 600)], Fraction(2)),
        VoiceSegment([Note(Pitch(27), 600)], Fraction(2)),
      ]),
    ]
  ),
  instruments = [
    Instrument(
      plugin = "https://surge-synthesizer.github.io/lv2/surge-xt",
      patch = {},
      data = {},
      uid = 600,
    ),
  ]
)

save_document('document.mide.zip', document)
