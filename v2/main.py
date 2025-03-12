from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.core.text import Label as CoreLabel
from music import resolution
import subprocess

from rhythm import (
    Zipper, Finger, Node, Branch, Leaf, finger_of, fold_of,
    branch, leaf, Uids, normalize, normalize_to, locate
)
import mid
import avl
import os

@dataclass
class Track:
    notes : avl.Avl # uid -> (onset, offset, pitch)
    trees : list[Node]
    head : Finger
    tail : Finger
    key  : list[int]

    def copy(self, **kwargs):
        if 'notes' not in kwargs:
            kwargs['notes'] = self.notes
        if 'trees' not in kwargs:
            kwargs['trees'] = self.trees
        if 'head' not in kwargs:
            kwargs['head'] = self.head
        if 'tail' not in kwargs:
            kwargs['tail'] = self.tail
        if 'key' not in kwargs:
            kwargs['key'] = self.key
        return Track(**kwargs)

import json
from notes import Pitch

def load(input_filename):
    with open(input_filename) as fd:
        data = json.load(fd)
    uids = Uids(data['last_uid'])
    notes = avl.empty
    for uid, (onset, offset, pitch) in data['notes']:
        notes = notes.insert(uid, (onset, offset, Pitch(*pitch)))
    def unserialize(trees):
        for tree in trees:
            w = tree["weight"]
            if "uid" in tree:
                yield Leaf(w, tree["uid"])
            else:
                yield Branch(w, tuple(unserialize(tree["children"])))
    rhythm = tuple(unserialize(data["rhythm"]))
    head = locate(rhythm, data["head"])
    tail = locate(rhythm, data["tail"])
    key = data["key"]
    return Track(notes, rhythm, head, tail, key), uids

def save(output_filename, track, uids):
    def serialize(tree):
        if isinstance(tree, Leaf):
            return {"weight": tree.weight, "uid": tree.uid}
        elif isinstance(tree, Branch):
            children = [serialize(n) for n in tree.children]
            return {"weight": tree.weight, "children": children}
    notes = []
    for uid, (onset, offset, pitch) in track.notes:
        notes.append((uid, (onset, offset, pitch.to_pair())))
    data = {
        "notes" : notes,
        "rhythm": [serialize(tree) for tree in track.trees],
        "head" : track.head.select(track.trees).strip(),
        "tail" : track.tail.select(track.trees).strip(),
        "key"  : track.key,
        "last_uid" : uids.index,
    }
    with open(output_filename, 'w') as fd:
        json.dump(data, fd)

def leftmost_finger(focus, pred):
    if isinstance(focus, (Leaf, int)):
        return pred
    return focus[0].leftmost_finger(Finger(pred, 0, len(focus)))

def rightmost_finger(focus, pred):
    if isinstance(focus, (Leaf, int)):
        return pred
    m = len(focus) - 1
    return focus[m].rightmost_finger(Finger(pred, m, len(focus)))

def zipup(trees, head, tail):
    zipper = None
    xfi, yfi = head.order(tail)
    d = xfi.common(yfi)
    d1 = xfi.depth
    d2 = yfi.depth
    while xfi.is_leftmost and d1 > d: # left trim
        xfi = xfi.pred
        d1 -= 1
    while yfi.is_rightmost and d2 > d: # right trim
        yfi = yfi.pred
        d2 -= 1
    ixs = xfi.unroll()
    iys = yfi.unroll()
    while len(ixs) and len(iys) and ixs[-1] == iys[-1]:
        ix = ixs[-1]
        ixs.pop()
        iys.pop()
        zipper = Zipper(zipper, trees[ix].weight, trees[:ix], trees[ix+1:])
        trees = trees[ix]
    return zipper, ixs, iys, trees

def erode(trees, head, tail):
    zipper, ixs, iys, focus = zipup(trees, head, tail)
    if len(ixs) == 0 or len(iys) == 0:
        return trees, head, tail
    while len(ixs) > 1 and len(iys) > 1:
        ix = ixs.pop()
        iy = iys.pop()
        side0 = focus[:ix]
        side1 = focus[iy+1:]
        w = focus[iy].weight
        cont = []
        for node in focus[ix:iy]:
            if isinstance(node, Branch):
                cont.extend(sn.op(lambda w: w*node.weight) for sn in node)
            else:
                cont.append(node)
            w += node.weight
        iys[-1] += len(cont)
        cont.extend(sn.op(lambda w: w*focus[iy].weight) for sn in focus[iy])
        if len(side0) + len(side1) != 0:
            zipper = Zipper(zipper, w, side0, side1)
        focus = normalize(cont)
    while len(ixs) > 1:
        ix = ixs.pop()
        ixs[-1] += ix
        iys[-1] += ix + len(focus[ix]) - ix - 1
        tw = sum(n.weight for n in focus[ix])
        side0 = [n.op(lambda w: w * tw) for n in focus[:ix]]
        side1 = [n.op(lambda w: w * tw) for n in focus[ix+1:]]
        focus = [n.op(lambda w: w * focus[ix].weight) for n in focus[ix]]
        focus = side0 + focus + side1
        assert iys[-1] < len(focus)
    while len(iys) > 1:
        iy = iys.pop()
        tw = sum(n.weight for n in focus[iy])
        side0 = [n.op(lambda w: w * tw) for n in focus[:iy]]
        side1 = [n.op(lambda w: w * tw) for n in focus[iy+1:]]
        focus = [n.op(lambda w: w * focus[iy].weight) for n in focus[iy]]
        focus = side0 + focus + side1
        iys[-1] += len(side0)
    base = finger_of(zipper)
    left = focus[ixs[0]].leftmost_finger(Finger(base, ixs[0], len(focus)))
    right = focus[iys[0]].rightmost_finger(Finger(base, iys[0], len(focus)))
    return fold_of(zipper, focus), left, right

def cut(trees, head, tail):
    zipper, ixs, iys, focus = zipup(trees, head, tail)
    if zipper is None:
        head, tail = head.order(tail)
        return trees, head, tail
    if len(ixs) > 0 and len(iys) > 0:
        if not (ixs[-1] == 0 and iys[-1] == len(focus) - 1):
            return cut(*group(trees, head, tail))
    this = focus
    left = ()
    right = ()
    while zipper:
        w = this.weight + sum(n.weight for n in left) + sum(n.weight for n in right)
        this = this.op(lambda w: w*zipper.weight)
        left = tuple(n.op(lambda w: w*zipper.weight) for n in left)
        left = tuple(n.op(lambda ww: ww*w) for n in zipper.left) + left
        if len(left) > 1 and zipper.pred:
            lw = sum(n.weight for n in left)
            left = (branch(lw, normalize(left)),)
        right = tuple(n.op(lambda w: w*zipper.weight) for n in right)
        right = right + tuple(n.op(lambda ww: ww*w) for n in zipper.right)
        if len(right) > 1 and zipper.pred:
            rw = sum(n.weight for n in right)
            right = (branch(rw, normalize(right)),)
        zipper = zipper.pred
    finger = Finger(None, len(left), len(left)+len(right)+1)
    head = leftmost_finger(this, finger)
    tail = rightmost_finger(this, finger)
    return (left + (this,) + right), head, tail

def erase(trees, head, tail):
    i = head.unroll()[-1]
    j = tail.unroll()[-1]
    x = min(i,j)
    y = max(i,j)
    m = len(trees) - (y+1 - x)
    if m == 0:
        return trees, head, tail, []
    rems = []
    for node in trees[x:y+1]:
        node.traverse(rems)
    trees = trees[:x] + trees[y+1:]
    finger0 = Finger(None, max(0, x-1), m)
    finger1 = Finger(None, min(x, m-1), m)
    head = finger0.select(trees).rightmost_finger(finger0)
    tail = finger1.select(trees).leftmost_finger(finger1)
    return trees, head, tail, rems

def insert_before(trees, head, tail, weight, uid):
    i = head.unroll()[-1]
    j = tail.unroll()[-1]
    x = min(i,j)
    return trees[:x] + (leaf(weight, uid),) + trees[x:], Finger(None, x, len(trees)+1)

def insert_after(trees, head, tail, weight, uid):
    i = head.unroll()[-1]
    j = tail.unroll()[-1]
    y = max(i,j)+1
    return trees[:y] + (leaf(weight, uid),) + trees[y:], Finger(None, y, len(trees)+1)

def capture(trees, head, tail):
    trees, head, tail = erode(trees, head, tail)
    trees, head, tail = group(trees, head, tail)
    _, _, _, focus = zipup(trees, head, tail)
    return focus

def paste(trees, head, tail, buffer, uids):
    trees, head, tail = erode(trees, head, tail)
    trees, head, tail = group(trees, head, tail)
    trees, finger, rems, _ = join(trees, head, tail, uids)
    zipper, _ = finger.zipper(trees)
    focus = buffer.clone(uids)
    base = zipper.finger
    left = focus.leftmost_finger(base)
    right = focus.rightmost_finger(base)
    return fold_of(zipper, focus.strip()), left, right, rems, focus.traverse([])
    
# TODO: reorder command, rearrange the tree.
#def reorder(trees, head, tail, direction):
#                    self.trees, self.head, self.tail = reorder(self.trees, self.head, self.tail, +1)
    
def resize(trees, head, tail, amount):
    i = head.unroll()[-1]
    j = tail.unroll()[-1]
    x = min(i,j)
    y = max(i,j)
    new_trees = []
    for k, tree in enumerate(trees):
        if x <= k <= y:
            tree = tree.op(lambda w: max(1, w+amount))
        new_trees.append(tree)
    return tuple(new_trees)

def group(trees, head, tail):
    zipper, ixs, iys, focus = zipup(trees, head, tail)
    if len(ixs) and len(iys):
        ix = ixs[-1]
        iy = iys[-1]
        n = len(focus)
        if ix + 1 <= iy and (n-iy-1+ix) > 0:
            w = sum(n.weight for n in focus[ix:iy+1])
            zipper = Zipper(zipper, w, focus[:ix], focus[iy+1:])
            focus = focus[ix:iy+1]
            base = finger_of(zipper)
            left = leftmost_finger(focus, base)
            right = rightmost_finger(focus, base)
            return fold_of(zipper, focus), left, right
        else:
            base = finger_of(zipper)
            left = leftmost_finger(focus, base)
            right = rightmost_finger(focus, base)
            return fold_of(zipper, focus), left, right
    else:
        base = finger_of(zipper)
        left = leftmost_finger(focus, base)
        right = rightmost_finger(focus, base)
        focus = focus.strip()
        return fold_of(zipper, focus), left, right

def join(trees, head, tail, uids):
    zipper, ixs, iys, focus = zipup(trees, head, tail)
    uid = next(uids)
    return fold_of(zipper, uid), finger_of(zipper), focus.traverse([]), uid

def split(trees, finger, divs, uids):
    zipper, old = finger.zipper(trees)
    focus = tuple(Leaf(w, next(uids)) for w in divs)
    base = zipper.finger
    left = leftmost_finger(focus, base)
    right = rightmost_finger(focus, base)
    return fold_of(zipper, focus), left, right, old, [n.uid for n in focus]

class RhythmTreeWidget(Widget):
    def __init__(self, **kwargs):
        super(RhythmTreeWidget, self).__init__(**kwargs)
        # Dictionary to store node positions for later lookup (x, y, width, height, depth)
        self.node_positions = {}

        # Rhythm tree
        input_filename = 'output.track.json'
        if os.path.exists(input_filename):
            self.track, self.uids = load(input_filename)
        else:
            self.uids  = Uids()
            self.track = Track(
                notes = avl.empty,
                trees = (
                    Leaf(4, next(self.uids)),
                    Leaf(4, next(self.uids)),
                    Leaf(4, next(self.uids)),
                    Leaf(4, next(self.uids)),
                ),
                head = Finger(None, 0, 4),
                tail = Finger(None, 0, 4),
                key = canon_key(1),
            )
        self.track_current = self.track
        self.track_undo = []
        self.track_redo = []

        self.buffer = Leaf(1, 0)
        self.buffer_notes = []

        self.mode = 'visual'
        self.octave_shift = 0
        self._keyboard = Window.request_keyboard(
            self._keyboard_closed, self, 'text')
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

        self.scroll_x = 0
        
        # Refresh drawing when the widget is resized or repositioned.
        self.bind(size=self.update_canvas, pos=self.update_canvas)
        self.update_canvas()

    def do(self, track):
        self.track_undo.append(self.track)
        self.track_redo = []
        self.track = track
        self.track_current = track
        self.update_canvas()

    def redo(self):
        if len(self.track_redo):
            self.track_undo.append(self.track_current)
            self.track = self.track_current = self.track_redo.pop()
            self.update_canvas()

    def undo(self):
        if len(self.track_undo):
            self.track_redo.append(self.track_current)
            self.track = self.track_current = self.track_undo.pop()
            self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.clear()
        self.node_positions = {}  # Reset stored positions
        
        track = self.track
        with self.canvas:
            # --- Draw the Rhythm Tree Grid --
            grid_width = max(self.width, 60*sum(node.weight for node in track.trees))
            xi = self.get_pos(track.trees, 0, grid_width, track.head.unroll())
            cursor_scroll = xi - self.width / 2
            self.scroll_x = max(self.scroll_x, cursor_scroll - self.width / 2 + 100)
            self.scroll_x = min(self.scroll_x, cursor_scroll + self.width / 2 - 100)
            offset_x = max(0, min(self.scroll_x, grid_width - self.width))
            row_height = 25
            max_depth = max(node.depth for node in track.trees)
            tree_area_height = (max_depth + 1) * row_height
            start_y = self.height - row_height  # start at top of widget
            self.draw_nodes(track.trees, -offset_x, start_y, grid_width, row_height, depth=0)

            # --- Draw the selection ---
            p = self.node_positions[track.head.select(track.trees).uid]
            q = self.node_positions[track.tail.select(track.trees).uid]
            x0 = min(p[0], q[0])
            x1 = max(p[0] + p[2], q[0] + q[2])
            if self.mode == 'visual':
                Color(0,1,1,0.5)
            else:
                Color(1,0.5,1,0.5)
            Rectangle(pos=(x0, 0), size=(x1-x0, self.height - tree_area_height))
            
            min_pitch = 30
            max_pitch = 38
            note_height = 10
            # --- Draw the Staff Area ---
            # Define a margin between the tree grid and staff area.
            staff_margin = 20
            staff_area_height = 120
            staff_area_top = self.height - tree_area_height - staff_margin
            staff_area_bottom = staff_area_top - staff_area_height

            staff_area_push = min(-self.octave_shift, 0)
            for uid, (start_id, end_id, pitch) in track.notes:
                staff_area_push = min(-(pitch.position - 38) // 7, staff_area_push)

            step = 7 / (max_pitch - min_pitch) * staff_area_height
            y_shift = step * staff_area_push

            # Draw 5 evenly spaced horizontal staff lines.
            num_lines = 5
            for i in range(num_lines):
                y_line = y_shift + staff_area_bottom + i * (staff_area_height / (num_lines - 1))
                Color(1, 1, 1)
                Line(points=[0, y_line, self.width, y_line], width=2)

            # --- Draw the Notes ---

            if self.mode == 'insert':
                Color(1,1,1, 0.5)
                position = 28 + self.octave_shift*7

                pitch_ratio = (position - min_pitch) / (max_pitch - min_pitch)
                y0 = staff_area_bottom + pitch_ratio * staff_area_height - note_height / 2

                pitch_ratio = (6 + position - min_pitch) / (max_pitch - min_pitch)
                y1 = staff_area_bottom + pitch_ratio * staff_area_height + note_height / 2

                Rectangle(pos=(x0, y0 + y_shift), size=(x1-x0, y1-y0))

            for uid, (start_id, end_id, pitch) in track.notes:
                # Ensure both start and end nodes exist in our stored positions.
                if start_id not in self.node_positions or end_id not in self.node_positions:
                    continue
                start_pos = self.node_positions[start_id]
                end_pos = self.node_positions[end_id]
                # The note starts at the left of the start node and ends at the right of the end node.
                note_x = start_pos[0] + 4
                note_width = (end_pos[0] + end_pos[2]) - start_pos[0] - 8
                # Map the MIDI pitch linearly within the staff area.
                pitch_ratio = (pitch.position - min_pitch) / (max_pitch - min_pitch)
                note_y = staff_area_bottom + pitch_ratio * staff_area_height - note_height / 2
                match pitch.accidental:
                    case  2: Color(1, 0.0, 1, 0.75)
                    case  1: Color(1, 0.5, 1, 0.75)
                    case  0: Color(1, 0.5, 0, 0.75)  # Use an orange color for the note.
                    case -1: Color(0, 0.5, 1, 0.75)
                    case -2: Color(0, 0.0, 1, 0.75)

                if pitch.accidental == track.key[pitch.position % 7] - resolution.base_key[pitch.position % 7]:
                    Color(1, 1, 1, 0.75)

                Line(rectangle=(note_x, note_y + y_shift, note_width, note_height), width=1)
                Rectangle(pos=(note_x, note_y + y_shift), size=(note_width, note_height))

    def get_pos(self, nodes, x, width, ixs):
        if len(ixs) == 0:
            return x + width / 2
        else:
            total_weight = sum(node.weight for node in nodes)
            ix = ixs.pop()
            x += sum(node.weight for node in nodes[:ix]) * width / total_weight
            return self.get_pos(nodes[ix], x, nodes[ix].weight * width / total_weight, ixs)
    
    def draw_nodes(self, nodes, x, y, width, height, depth):
        total_weight = sum(node.weight for node in nodes)
        current_x = x
        for node in nodes:
            node_width = width * (node.weight / total_weight)
            self.draw_node(node, current_x, y, node_width, height, depth)
            current_x += node_width

    def draw_node(self, node, x, y, width, height, depth):
        """Draws a node rectangle with text and recursively draws its children."""
        
        # Draw the node rectangle.
        Color(0.2 + 0.2 * depth, 0.5, 0.8, 1)
        Rectangle(pos=(x, y), size=(width, height))
        Color(0, 0, 0)
        Line(rectangle=(x, y, width, height), width=1)

        # Render the node's label (tag and weight) centered in the rectangle.
        text = f"{node.weight}"
        label = CoreLabel(text=text, font_size=14)
        label.refresh()
        texture = label.texture
        tx = x + (width - texture.width) / 2
        ty = y + (height - texture.height) / 2
        Color(0, 0, 0, 1)
        Rectangle(texture=texture, pos=(tx, ty), size=texture.size)

        if isinstance(node, Branch):
             self.draw_nodes(node.children, x, y - height, width, height, depth+1)
        else:
             self.node_positions[node.uid] = (x, y, width, height, depth)
        
#        else:
#            Color(1, 1, 1)
#            Line(points=[x+width, y, x+width, 0], width=2)

    def _keyboard_closed(self):
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        track = self.track
        match (keycode[1], self.mode):
            case 'z', 'visual':
                self.undo()
            case 'x', 'visual':
                self.redo()
            case 'up', 'insert':
                self.octave_shift += 1
                self.update_canvas()
            case 'down', 'insert':
                self.octave_shift -= 1
                self.update_canvas()
            case 'left', _:
                if finger := track.head.prev_uid(track.trees):
                    if 'shift' in modifiers:
                        self.track = self.track.copy(head = finger)
                    else:
                        self.track = self.track.copy(head = finger, tail = finger)
                    self.update_canvas()
            case 'right', _:
                if finger := track.head.next_uid(track.trees):
                    if 'shift' in modifiers:
                        self.track = self.track.copy(head = finger)
                    else:
                        self.track = self.track.copy(head = finger, tail = finger)
                    self.update_canvas()
            case 'e', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_erode(track):
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case 'g', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_erode(track):
                    trees, head, tail = group(track.trees, track.head, track.tail)
                    track = track.copy(trees = trees, head = head, tail = tail)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case '+', 'visual':
                trees = resize(track.trees, track.head, track.tail, 1)
                track = track.copy(trees = trees)
                self.do(track)
            case '-', 'visual':
                trees = resize(track.trees, track.head, track.tail, -1)
                track = track.copy(trees = trees)
                self.do(track)
            #case 'q':
            #    invert = not self.head <= self.tail
            #    if self.safe_erode():
            #        self.trees, self.head, self.tail = group(self.trees, self.head, self.tail)
            #        self.trees, self.head, self.tail = reorder(self.trees, self.head, self.tail, -1)
            #        if invert:
            #            self.head, self.tail = self.tail, self.head
            #        self.update_canvas()
            #case 'w':
            #    invert = not self.head <= self.tail
            #    if self.safe_erode():
            #        self.trees, self.head, self.tail = group(self.trees, self.head, self.tail)
            #        self.trees, self.head, self.tail = reorder(self.trees, self.head, self.tail, +1)
            #        if invert:
            #            self.head, self.tail = self.tail, self.head
            #        self.update_canvas()
            case 'y', 'visual':
                self.buffer = capture(track.trees, track.head, track.tail)
                uids = self.buffer.traverse([])
                self.buffer_notes = []
                for uid, (onset, offset, pitch) in track.notes:
                    if (onset in uids) and (onset in uids):
                        self.buffer_notes.append((uid, (onset, offset, pitch)))
            case 'p', 'visual':
                invert = not track.head <= track.tail
                notes = track.notes
                trees, head, tail, rems, intrs = paste(track.trees, track.head, track.tail, self.buffer, self.uids)
                uids = self.buffer.traverse([])
                mapping = dict(zip(uids, intrs))
                for uid, (onset, offset, pitch) in self.buffer_notes:
                    onset = mapping[onset]
                    offset = mapping[offset]
                    notes = notes.insert(next(self.uids), (onset, offset, pitch))

                track = Track(notes = notes, trees = trees, head = head, tail = tail)
                if invert:
                    track = track.copy(head = track.tail, tail = track.head)
                self.do(track)
            case 'c', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case 'i', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    trees, head = insert_before(track.trees, track.head, track.tail, 1, next(self.uids))
                    track = track.copy(trees = trees, head = head, tail = head)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case 'o', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    trees, head = insert_after(track.trees, track.head, track.tail, 1, next(self.uids))
                    track = track.copy(trees = trees, head = head, tail = head)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case 'backspace', 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    trees, head, tail, rems = erase(track.trees, track.head, track.tail)
                    notes = track.notes
                    for uid, (onset, offset, pitch) in notes:
                        if (onset in rems) or (onset in rems):
                            notes = notes.delete(uid)
                    track = track.copy(notes = notes, trees = trees, head = head, tail = tail)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            case '1', 'visual':
                if track := self.safe_erode(track):
                    trees, head, tail = group(track.trees, track.head, track.tail)
                    trees, head, rems, intr = join(trees, head, tail, self.uids)
                    tail = head
                    notes = track.notes
                    for uid, (onset, offset, pitch) in notes:
                        if (onset in rems) or (onset in rems):
                            if onset in rems:
                                onset = intr
                            if offset in rems:
                                offset = intr
                            notes = notes.insert(uid, (onset, offset, pitch))
                    track = track.copy(notes = notes, trees = trees, head = head, tail = tail)
                    self.do(track)
            case '2', 'visual':
                self.do_split([1,1])
                self.update_canvas()
            case '3', 'visual':
                self.do_split([1,1,1])
                self.update_canvas()
            case '4', 'visual':
                self.do_split([3,1])
                self.update_canvas()
            case '5', 'visual':
                self.do_split([1,3])
                self.update_canvas()
            case '6', 'visual':
                self.do_split([1,1,1,1])
                self.update_canvas()
            case '7', 'visual':
                self.do_split([3,2])
                self.update_canvas()
            case '8', 'visual':
                self.do_split([2,3])
                self.update_canvas()
            case 's', 'visual':
                save("output.track.json", track, self.uids)
                mid.save("output.mid", track.trees, track.notes, tempo=80)
                subprocess.Popen(["timidity", "output.mid"])
            case 'escape', _:
                self.mode = 'visual'
                self.update_canvas()
            case 'spacebar', 'visual':
                self.mode = 'insert'
                self.update_canvas()
        #        keyboard.release()
            case 'a', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(28), mod)
                self.update_canvas()
            case 's', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(29), mod)
                self.update_canvas()
            case 'd', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(30), mod)
                self.update_canvas()
            case 'f', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(31), mod)
                self.update_canvas()
            case 'g', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(32), mod)
                self.update_canvas()
            case 'h', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(33), mod)
                self.update_canvas()
            case 'j', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(34), mod)
                self.update_canvas()

            case 'q', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(28, 1), mod)
                self.update_canvas()
            case 'w', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(29, 1), mod)
                self.update_canvas()
            case 'e', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(30, 1), mod)
                self.update_canvas()
            case 'r', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(31, 1), mod)
                self.update_canvas()
            case 't', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(32, 1), mod)
                self.update_canvas()
            case 'y', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(33, 1), mod)
                self.update_canvas()
            case 'u', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(34, 1), mod)
                self.update_canvas()

            case 'z', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(28, -1), mod)
                self.update_canvas()
            case 'x', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(29, -1), mod)
                self.update_canvas()
            case 'c', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(30, -1), mod)
                self.update_canvas()
            case 'v', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(31, -1), mod)
                self.update_canvas()
            case 'b', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(32, -1), mod)
                self.update_canvas()
            case 'n', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(33, -1), mod)
                self.update_canvas()
            case 'm', 'insert':
                mod = 'shift' in modifiers or 'capslock' in modifiers
                self.insert_note(Pitch(34, -1), mod)
                self.update_canvas()

            case _:
                print(' - text is %r' % text)
                print(' - modifiers are %r' % modifiers)
        return True

    def insert_note(self, pitch, multi):
        track = self.track
        uids = []
        for tree in track.trees:
            tree.traverse(uids)
        uid_index = {uid:index for index, uid in enumerate(uids)}

        start, end = track.head.order(track.tail)
        onset = start.select(track.trees).strip()
        offset = end.select(track.trees).strip()

        pitch = Pitch(pitch.position + self.octave_shift*7, pitch.accidental)

        insertion = True
        start0, end0 = uid_index[onset], uid_index[offset]
        notes = track.notes
        for uid, (onset1, offset1, pitch1) in notes:
            start1, end1 = uid_index[onset1], uid_index[offset1]
            if pitch == pitch1 and max(start0, start1) <= min(end0, end1):
                notes = notes.delete(uid)
                insertion = False
        if insertion and multi:
            for i in range(uid_index[onset], uid_index[offset]+1):
                t = uids[i]
                notes = notes.insert(next(self.uids), (t, t, pitch))
        elif insertion:
            notes = notes.insert(next(self.uids), (onset, offset, pitch))
        track = track.copy(notes = notes)
        self.do(track)

    def safe_erode(self, track):
        total = sum(n.weight for n in track.trees)
        trees, head, tail = erode(track.trees, track.head, track.tail)
        if trees := normalize_to(trees, total):
            track = track.copy(trees = trees, head = head, tail = tail)
            return track

    def safe_cut(self, track):
        total = sum(n.weight for n in track.trees)
        trees, head, tail = erode(track.trees, track.head, track.tail)
        trees, head, tail = cut(trees, head, tail)
        if trees := normalize_to(trees, total):
            track = track.copy(trees = trees, head = head, tail = tail)
            return track

    def do_split(self, divs):
        track = self.track
        invert = not track.head <= track.tail
        if track := self.safe_erode(track):
            old_times = {}
            mid.compute_times(track.trees, old_times)

            trees, head, tail = group(track.trees, track.head, track.tail)
            trees, head, rems, intr = join(trees, head, tail, self.uids)
            trees, head, tail, rem, intrs = split(trees, head, divs, self.uids)
            track = track.copy(trees = trees, head = head, tail = tail)

            new_times = {}
            mid.compute_times(track.trees, new_times)

            notes = track.notes
            for uid, (onset, offset, pitch) in notes:
                change = False
                if onset in rems or offset in rems:
                    if onset in rems:
                        o = old_times[onset][0]
                        onset = min((abs(new_times[i][0] - o), i) for i in intrs)[1]
                    if offset in rems:
                        o = old_times[offset][0] + old_times[offset][1]
                        offset = min((abs(new_times[i][0] + new_times[i][1] - o), i) for i in intrs)[1]
                    notes = notes.insert(uid, (onset, offset, pitch))
            track = track.copy(notes = notes)
            if invert:
                track = track.copy(head = track.tail, tail = track.head)
            self.do(track)

class RhythmTreeApp(App):
    def build(self):
        return RhythmTreeWidget()

if __name__ == "__main__":
    RhythmTreeApp().run()

