from entities import *
from resolution import *

print('midi: 60')
print(list(enharmonics(60)))
print('midi: 69')
print(list(enharmonics(69)))

print('chord problem')
enh = list(chord_enharmonics([60, 61]))
print(min(enh, key=lambda k: sum(map(pitch_complexity, k))))

# Example usage
fraction = Fraction(3, 16)  # Example for a dotted eighth note
print(categorize_note_duration(fraction))
fraction = Fraction(1, 4*3)
print(categorize_note_duration(fraction))

# Example usage
for i in range(11):
    quantized_fraction = quantize_fraction(0.111 * i)
    print(f"input {0.111 * i}")
    print(f"Quantized Fraction: {quantized_fraction}")
    print(categorize_note_duration(quantized_fraction))
