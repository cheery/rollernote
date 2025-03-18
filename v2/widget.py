from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from .music import resolution
from .music.notes import Pitch
import subprocess
import io
import random

from .rhythm import (
    Zipper, Finger, Node, Branch, Leaf, finger_of, fold_of,
    branch, leaf, Uids, normalize, normalize_to, normalize_tof, locate
)
from . import mid
from . import avl
import os

from visual.font import FontEngine
from visual.gui6 import Node
from visual import gui6

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

def weighed_capture(trees, head, tail):
    total_weight = sum(node.weight for node in trees)
    trees, head, tail = erode(trees, head, tail)
    trees, head, tail = group(trees, head, tail)
    trees = normalize_tof(trees, total_weight)
    zipper, _, _, focus = zipup(trees, head, tail)
    if zipper is None:
        total = sum(node.weight for node in focus)
        return Branch(total, focus)
    w = zipper.weight
    while zipper.pred:
        w *= zipper.pred.weight / zipper.total_weight
        zipper = zipper.pred
    focus = focus.op(lambda _: w)
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



class Widget(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
                key = resolution.canon_key(1),
            )
        self.track_current = self.track
        self.track_undo = []
        self.track_redo = []

        self.buffer = Leaf(1, 0)
        self.buffer_notes = []

        self.mode = 'visual'
        self.octave_shift = 0

        self.scroll = [0,0]

    def do(self, track):
        self.track_undo.append(self.track)
        self.track_redo = []
        self.track = track
        self.track_current = track

    def redo(self):
        if len(self.track_redo):
            self.track_undo.append(self.track_current)
            self.track = self.track_current = self.track_redo.pop()

    def undo(self):
        if len(self.track_undo):
            self.track_redo.append(self.track_current)
            self.track = self.track_current = self.track_undo.pop()

    def pre_draw(self, ui, x, y):
        left, bottom, cwidth, cheight = self.rect.offset(x,y)

        track = self.track
        grid_width = max(cwidth, 60*sum(node.weight for node in track.trees))
        self.node_positions = self.layout_nodes(track.trees, 0, grid_width, {})
        
        # --- Draw the Rhythm Tree Grid --
        xi = self.get_pos(track.trees, 0, grid_width, track.head.unroll())
        cursor_scroll = xi - cwidth / 2
        self.scroll[0] = max(self.scroll[0], cursor_scroll - cwidth / 2 + 100)
        self.scroll[0] = min(self.scroll[0], cursor_scroll + cwidth / 2 - 100)
        scroll_x = max(0, min(self.scroll[0], grid_width - cwidth))
        row_height = 25
        max_depth = max(node.depth for node in track.trees)
        tree_area_height = (max_depth + 1) * row_height
        start_y = cheight - row_height  # start at top of widget
        self.draw_nodes(ui, track.trees, -scroll_x, start_y, grid_width, row_height, depth=0)

        # --- Draw the selection ---
        p = self.node_positions[track.head.select(track.trees).uid]
        q = self.node_positions[track.tail.select(track.trees).uid]
        x0 = min(p[0], q[0])
        x1 = max(p[0] + p[1], q[0] + q[1])
        if self.mode == 'visual':
            color = 0,1,1,0.5
        else:
            color = 1,0.5,1,0.5
        gui6.fill(ui, color,
            (x0 - scroll_x, 0, x1-x0, cheight - tree_area_height))

        min_pitch = 30
        max_pitch = 38
        note_height = 10
        # --- Draw the Staff Area ---
        # Define a margin between the tree grid and staff area.
        staff_margin = 20
        staff_area_height = 120
        staff_area_top = cheight - tree_area_height - staff_margin
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
            gui6.trace(ui,
                (1,1,1,1),
                (0, y_line, cwidth, 0))

        # --- Draw the Notes ---

        if self.mode == 'insert':
            color = 1,1,1,0.5
            position = 28 + self.octave_shift*7

            pitch_ratio = (position - min_pitch) / (max_pitch - min_pitch)
            y0 = staff_area_bottom + pitch_ratio * staff_area_height - note_height / 2

            pitch_ratio = (6 + position - min_pitch) / (max_pitch - min_pitch)
            y1 = staff_area_bottom + pitch_ratio * staff_area_height + note_height / 2

            gui6.fill(ui, color,
              (x0-scroll_x, y0+y_shift, x1-x0, y1-y0))

        for uid, (start_id, end_id, pitch) in track.notes:
            # Ensure both start and end nodes exist in our stored positions.
            if start_id not in self.node_positions or end_id not in self.node_positions:
                continue
            start_pos = self.node_positions[start_id]
            end_pos = self.node_positions[end_id]
            # The note starts at the left of the start node and ends at the right of the end node.
            note_x = start_pos[0] + 4
            note_width = (end_pos[0] + end_pos[1]) - start_pos[0] - 8
            # Map the MIDI pitch linearly within the staff area.
            pitch_ratio = (pitch.position - min_pitch) / (max_pitch - min_pitch)
            note_y = staff_area_bottom + pitch_ratio * staff_area_height - note_height / 2
            match pitch.accidental:
                case  2: color = (1, 0.0, 1, 0.75)
                case  1: color = (1, 0.5, 1, 0.75)
                case  0: color = (1, 0.5, 0, 0.75)  # Use an orange color for the note.
                case -1: color = (0, 0.5, 1, 0.75)
                case -2: color = (0, 0.0, 1, 0.75)

            if pitch.accidental == track.key[pitch.position % 7] - resolution.base_key[pitch.position % 7]:
                color = (1, 1, 1, 0.75)

            gui6.trace(ui, color,(note_x - scroll_x, note_y + y_shift, note_width, note_height))
            gui6.fill(ui, color,(note_x - scroll_x, note_y + y_shift, note_width, note_height))

        for key in ui.keyboard:
            if isinstance(key, gui6.Down):
                self.process_keydown(*key)

    def get_pos(self, nodes, x, width, ixs):
        if len(ixs) == 0:
            return x + width / 2
        else:
            total_weight = sum(node.weight for node in nodes)
            ix = ixs.pop()
            x += sum(node.weight for node in nodes[:ix]) * width / total_weight
            return self.get_pos(nodes[ix], x, nodes[ix].weight * width / total_weight, ixs)

    def layout_nodes(self, nodes, x, width, node_positions):
        total_weight = sum(node.weight for node in nodes)
        current_x = x
        for node in nodes:
            node_width = width * (node.weight / total_weight)
            if isinstance(node, Branch):
                 self.layout_nodes(node.children, current_x, node_width, node_positions)
            else:
                 node_positions[node.uid] = (current_x, node_width)

            current_x += node_width
        return node_positions
    
    def draw_nodes(self, ui, nodes, x, y, width, height, depth):
        total_weight = sum(node.weight for node in nodes)
        current_x = x
        for node in nodes:
            node_width = width * (node.weight / total_weight)
            self.draw_node(ui, node, current_x, y, node_width, height, depth)
            current_x += node_width

    def draw_node(self, ui, node, x, y, width, height, depth):
        """Draws a node rectangle with text and recursively draws its children."""
        
        # Draw the node rectangle.
        gui6.fill(ui,
            (0.2 + 0.2 * depth, 0.5, 0.8, 1),
            (x,y,width,height))
        gui6.trace(ui,
            (0,0,0,1),
            (x,y,width,height))

        # Render the node's label (tag and weight) centered in the rectangle.
        rect = gui6.Rect(x,y,width,height)
        text = f"{node.weight}"
        font = ui.mem(FontEngine, int(16))
        text_width = font.measure(text)
        font.prepare((0,0,0,1))
        font.text(text,
            rect.hcenter - text_width / 2,
            rect.bottom + font.descent)
        font.finish()
 
        if isinstance(node, Branch):
             self.draw_nodes(ui, node.children, x, y - height, width, height, depth+1)

    def process_keydown(self, sym, repeat, modifiers):
        track = self.track
        match (sym, self.mode):
            # Z
            case 122, 'visual':
                self.undo()
            # X
            case 120, 'visual':
                self.redo()
            # up
            case 1073741906, 'insert':
                self.octave_shift += 1
            # down
            case 1073741905, 'insert':
                self.octave_shift -= 1
            # left
            case 1073741904, _:
                if finger := track.head.prev_uid(track.trees):
                    if 0 != 2 & modifiers:
                        self.track = self.track.copy(head = finger)
                    else:
                        self.track = self.track.copy(head = finger, tail = finger)
            # right
            case 1073741903, _:
                if finger := track.head.next_uid(track.trees):
                    if 0 != 2 & modifiers:
                        self.track = self.track.copy(head = finger)
                    else:
                        self.track = self.track.copy(head = finger, tail = finger)
            # e
            case 101, 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_erode(track):
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            # g
            case 103, 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_erode(track):
                    trees, head, tail = group(track.trees, track.head, track.tail)
                    track = track.copy(trees = trees, head = head, tail = tail)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            # +
            case 43, 'visual':
                trees = resize(track.trees, track.head, track.tail, 1)
                track = track.copy(trees = trees)
                self.do(track)
            # -
            case 45, 'visual':
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
            #case 'w':
            #    invert = not self.head <= self.tail
            #    if self.safe_erode():
            #        self.trees, self.head, self.tail = group(self.trees, self.head, self.tail)
            #        self.trees, self.head, self.tail = reorder(self.trees, self.head, self.tail, +1)
            #        if invert:
            #            self.head, self.tail = self.tail, self.head
            # y
            case 121, 'visual':
                self.buffer = capture(track.trees, track.head, track.tail)
                uids = self.buffer.traverse([])
                self.buffer_notes = []
                for uid, (onset, offset, pitch) in track.notes:
                    if (onset in uids) and (onset in uids):
                        self.buffer_notes.append((uid, (onset, offset, pitch)))
            # p
            case 112, 'visual':
                invert = not track.head <= track.tail
                notes = track.notes
                trees, head, tail, rems, intrs = paste(track.trees, track.head, track.tail, self.buffer, self.uids)
                uids = self.buffer.traverse([])
                mapping = dict(zip(uids, intrs))
                for uid, (onset, offset, pitch) in self.buffer_notes:
                    onset = mapping[onset]
                    offset = mapping[offset]
                    notes = notes.insert(next(self.uids), (onset, offset, pitch))

                track = track.copy(notes = notes, trees = trees, head = head, tail = tail)
                if invert:
                    track = track.copy(head = track.tail, tail = track.head)
                self.do(track)
            # c
            case 99, 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            # i
            case 105, 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    trees, head = insert_before(track.trees, track.head, track.tail, 1, next(self.uids))
                    track = track.copy(trees = trees, head = head, tail = head)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            # o
            case 111, 'visual':
                invert = not track.head <= track.tail
                if track := self.safe_cut(track):
                    trees, head = insert_after(track.trees, track.head, track.tail, 1, next(self.uids))
                    track = track.copy(trees = trees, head = head, tail = head)
                    if invert:
                        track = track.copy(head = track.tail, tail = track.head)
                    self.do(track)
            # backspace
            case 8, 'visual':
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
            # 1
            case 49, 'visual':
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
            # 2
            case 50, 'visual':
                self.do_split([1,1])
            # 3
            case 51, 'visual':
                self.do_split([1,1,1])
            # 4
            case 52, 'visual':
                self.do_split([3,1])
            # 5
            case 53, 'visual':
                self.do_split([1,3])
            # 6
            case 54, 'visual':
                self.do_split([1,1,1,1])
            # 7
            case 55, 'visual':
                self.do_split([3,2])
            # 8
            case 56, 'visual':
                self.do_split([2,3])
            # s
            case 115, 'visual':
                save("output.track.json", track, self.uids)
                #mid.save("output.mid", track.trees, track.notes, tempo=80)
                #subprocess.Popen(["timidity", "output.mid"])
            # tab
            case 9, _:
                self.preview(track)
            # escape
            case 27, _:
                self.mode = 'visual'
            # spacebar
            case 32, 'visual':
                self.mode = 'insert'
        #        keyboard.release()
            # a
            case 97, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(28), mod)
            # s
            case 115, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(29), mod)
            # d
            case 100, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(30), mod)
            # f
            case 102, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(31), mod)
            # g
            case 103, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(32), mod)
            # h
            case 104, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(33), mod)
            # j
            case 106, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(34), mod)

            # q
            case 113, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(28, 1), mod)
            # w
            case 119, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(29, 1), mod)
            # e
            case 101, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(30, 1), mod)
            # r
            case 114, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(31, 1), mod)
            # t
            case 116, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(32, 1), mod)
            # y
            case 121, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(33, 1), mod)
            # u
            case 117, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(34, 1), mod)

            # z
            case 122, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(28, -1), mod)
            # x
            case 120, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(29, -1), mod)
            # c
            case 99, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(30, -1), mod)
            # v
            case 118, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(31, -1), mod)
            # b
            case 98, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(32, -1), mod)
            # n
            case 110, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(33, -1), mod)
            # m
            case 109, 'insert':
                mod = 0 != 8194 & modifiers # shift or capslock
                self.insert_note(Pitch(34, -1), mod)

            case _:
                print(' - sym is %r' % sym)
                print(' - modifiers are %r' % modifiers)
        return True

    def preview(self, track):
        if self.mode == 'visual':
            mi = mid.midifile(track.trees, track.notes, tempo=80, program=0)#random.randint(0, 127))
        else:
            tree = weighed_capture(track.trees, track.head, track.tail)
            mi = mid.midifile([tree], track.notes, tempo=80, program=0)#random.randint(0, 127))
        self.player = subprocess.Popen(["timidity", "-"], stdin=subprocess.PIPE)
        mi.save(file=self.player.stdin)
        self.player.stdin.flush()

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
        if insertion:
            self.preview(track)
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
