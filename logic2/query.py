from .avl import empty
from .structures import Variable, Structure

def can_unify(pat, key):
    if isinstance(pat, Variable):
        return True
    elif isinstance(pat, tuple) and isinstance(key, tuple):
        if len(pat) == len(key):
            return all(can_unify(x,y) for x,y in zip(pat, key))
        else:
            return False
    elif isinstance(pat, Structure) and isinstance(key, Structure):
        if pat.functor == key.functor:
            return can_unify(pat.args, key.args)
        else:
            return False
    else:
        return pat == key

def can_be_less(pat, key):
    if isinstance(pat, Variable):
        return True
    elif isinstance(pat, tuple) and isinstance(key, tuple):
        if len(pat) == len(key):
            for x,y in zip(pat, key):
                if can_be_less(x,y):
                    return True
                if not can_unify(x,y):
                    return False
            return False
        else:
            return len(pat) < len(key)
    elif isinstance(pat, Structure) and isinstance(key, Structure):
        if pat.functor == key.functor:
            return can_be_less(pat.args, key.args)
        else:
            return pat.functor < key.functor
    else:
        return pat < key

def can_be_greater(pat, key):
    if isinstance(pat, Variable):
        return True
    elif isinstance(pat, tuple) and isinstance(key, tuple):
        if len(pat) == len(key):
            for x,y in zip(pat, key):
                if can_be_greater(x,y):
                    return True
                if not can_unify(x,y):
                    return False
            return False
        else:
            return len(pat) > len(key)
    elif isinstance(pat, Structure) and isinstance(key, Structure):
        if pat.functor == key.functor:
            return can_be_greater(pat.args, key.args)
        else:
            return pat.functor > key.functor
    else:
        return pat > key

def query_pattern(a, pat):
    if a is not empty:
        if can_be_less(pat, a.key):
            yield from query_pattern(a.left, pat)
        if can_unify(pat, a.key):
            yield a.key, a.value
        if can_be_greater(pat, a.key):
            yield from query_pattern(a.right, pat)
