from fractions import Fraction
from entities import *

document = Document(
  track = Track([
    [
      VoiceSegment([Pitch(32, +1)], Fraction(4)),
      VoiceSegment([Pitch(32)], Fraction(2)),
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
    ],
    [
      VoiceSegment([Pitch(24)], Fraction(2)),
      VoiceSegment([Pitch(25)], Fraction(2)),
      VoiceSegment([Pitch(26)], Fraction(2)),
      VoiceSegment([Pitch(27)], Fraction(2)),
    ]
  ]),
  instrument = Instrument(
      plugin = "https://surge-synthesizer.github.io/lv2/surge-xt",
      patch = {},
      data = {}
  ),
)

save_document('document.mide.zip', document)
