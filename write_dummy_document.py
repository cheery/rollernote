from fractions import Fraction
from entities import *

document = Document(
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
      Voice(300, 100, [
        VoiceSegment([Pitch(32, +1)], Fraction(4)),
        VoiceSegment([Pitch(32)], Fraction(2)),
        VoiceSegment([Pitch(32)], Fraction(1)),
        VoiceSegment([Pitch(32)], Fraction(1)),
        VoiceSegment([Pitch(36)], Fraction(1)),
        VoiceSegment([Pitch(38)], Fraction(1)),
        VoiceSegment([Pitch(40)], Fraction(1, 2)),
        VoiceSegment([],         Fraction(1, 2)),
        VoiceSegment([Pitch(34, -1)], Fraction(1)),
        VoiceSegment([Pitch(35)], Fraction(1, 2)),
        VoiceSegment([Pitch(36)], Fraction(1, 4)),
        VoiceSegment([Pitch(37)], Fraction(1, 8)),
        VoiceSegment([Pitch(37)], Fraction(1, 16)),
        VoiceSegment([Pitch(37), Pitch(30)], Fraction(3, 16)),
        VoiceSegment([Pitch(37)], Fraction(1, 4) + Fraction(1, 8) + Fraction(1, 16)),
        VoiceSegment([Pitch(37)], Fraction(1, 3)),
      ]),
      Voice(400, 100, [
        VoiceSegment([Pitch(24)], Fraction(2)),
        VoiceSegment([Pitch(25)], Fraction(2)),
        VoiceSegment([Pitch(26)], Fraction(2)),
        VoiceSegment([Pitch(27)], Fraction(2)),
      ]),
      Voice(500, 200, [
        VoiceSegment([Pitch(24)], Fraction(2)),
        VoiceSegment([Pitch(25)], Fraction(2)),
        VoiceSegment([Pitch(26)], Fraction(2)),
        VoiceSegment([Pitch(27)], Fraction(2)),
      ]),
    ]
  ),
  instrument = Instrument(
      plugin = "https://surge-synthesizer.github.io/lv2/surge-xt",
      patch = {},
      data = {}
  ),
)

save_document('document.mide.zip', document)
