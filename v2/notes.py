class Pitch:
    def __init__(self, position, accidental=0):
        self.position = position
        self.accidental = accidental
        assert position is not None
        assert accidental is not None

    def __repr__(self):
        a = ['bb', 'b', 'n', 's', 'ss'][self.accidental+2]
        return f"{a}{self.position}"

    def to_pair(self):
        return self.position, self.accidental

    def __eq__(self, other):
        return self.to_pair() == other.to_pair()

    def __hash__(self):
        return hash(self.to_pair())
