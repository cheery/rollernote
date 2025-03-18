import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage
from .rhythm import (
    Zipper, Finger, Branch, Leaf, finger_of, fold_of,
    branch, leaf, Uids
)
from .music import resolution

def save(output_filename, trees, notes, tempo, ticks_per_beat=480):
    mid = midifile(trees, notes, tempo, ticks_per_beat)
    mid.save(output_filename)
    print(f"MIDI file saved as '{output_filename}'.")

def midifile(trees, notes, tempo, ticks_per_beat=480, program=0):
    print(f"MIDI program {program}")
    node_times = {}  # uid -> (start_beat, duration_in_beats)
    compute_times(trees, node_times)
    
    events = []  # List of events as tuples: (tick, type, pitch, velocity)
    for uid, (on,off,pitch) in notes:
         if on not in node_times or off not in node_times:
             continue
         onset = node_times[on][0]
         offset = node_times[off][0] + node_times[off][1]
         start = int(onset * ticks_per_beat)
         end   = int(offset * ticks_per_beat)
         pitch = resolution.resolve_pitch(pitch)
         events.append((start, 'note_on',  pitch, 127))
         events.append((end,   'note_off', pitch, 64))
    events.sort(key=lambda x: x[0])
    
    # === Create the MIDI File ===
    mid = MidiFile(ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    mid.tracks.append(track)
    
    tempo = mido.bpm2tempo(tempo)
    track.append(MetaMessage('set_tempo', tempo=tempo, time=0))
    track.append(Message('program_change', program=program, time=0, channel=0))
    
    # Add MIDI events to the track with appropriate delta times.
    last_tick = 0
    for tick, event_type, pitch, velocity in events:
        delta = tick - last_tick
        last_tick = tick
        msg = Message(event_type, note=pitch, velocity=velocity, time=delta)
        track.append(msg)

    return mid

def compute_times(trees, node_times):
    x = 0
    for tree in trees:
        compute_node_times(tree, x, tree.weight, node_times)
        x += tree.weight

def compute_node_times(tree, start, duration, node_times):
    if isinstance(tree, Leaf):
        node_times[tree.uid] = (start, duration)
    else:
        total_weight = sum(child.weight for child in tree.children)
        current_start = start
        for child in tree.children:
            child_duration = duration * (child.weight / total_weight)
            compute_node_times(child, current_start, child_duration, node_times)
            current_start += child_duration

if __name__ == '__main__':
    main()

