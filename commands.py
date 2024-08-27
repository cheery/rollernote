"""
    Commands record actions made for document.
"""
import gui

class DemoCommand:
    def __init__(self):
        self.name = "demo command added during init"
    def do(self, document):
        print('done')
    def undo(self, document):
        print('undone')

class History:
    def __init__(self, document):
        self.document = document
        self.undo_stack = []
        self.redo_stack = []

    def do(self, command):
        self.redo_stack.clear()
        command.do(self.document)
        self.undo_stack.append(command)

    def undo(self):
        command = self.undo_stack.pop()
        command.undo(self.document)
        self.redo_stack.append(command)

    def redo(self):
        command = self.redo_stack.pop()
        command.do(self.document)
        self.undo_stack.append(command)
