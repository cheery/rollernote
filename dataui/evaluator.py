from kiwisolver import Solver, Variable as LVariable
from immutables import Map
from collections import namedtuple
import operator as op

def left(rc):
    return rc[0]

def bottom(rc):
    return rc[1]

def right(rc):
    return rc[0] + rc[2]

def top(rc):
    return rc[1] + rc[3]

def xcenter(rc):
    return (left(rc) + right(rc)) / 2

def ycenter(rc):
    return (top(rc) + bottom(rc)) / 2

def width(rc):
    return rc[2]

def height(rc):
    return rc[3]

class Variable:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return f"Variable({repr(self.name)})"

Term = namedtuple('Term', ['functor', 'args'])
Call = namedtuple('Call', ['func', 'args'])

def unify(u, v, subs):
    u = step(u, subs)
    v = step(v, subs)
    if isinstance(u, Variable) and isinstance(v, Variable) and u is v:
        return subs
    elif isinstance(u, Variable):
        v = walk(v, subs)
        if not occurs(u, v):
            return subs.set(u, v)
    elif isinstance(v, Variable):
        u = walk(u, subs)
        if not occurs(v, u):
            return subs.set(v, u)
    elif isinstance(u, Term) and isinstance(v, Term):
        if u.functor == v.functor and len(u.args) == len(v.args):
            for a,b in zip(u.args, v.args):
                subs = unify(a, b, subs)
                if subs is None:
                    return None
            return subs
    elif isinstance(u, tuple) and isinstance(v, tuple):
        if len(u) == len(v):
            for a,b in zip(u, v):
                subs = unify(a, b, subs)
                if subs is None:
                    return None
            return subs
    elif u == v:
        return subs

def occurs(var, t):
    if var is t:
        return True
    if isinstance(t, Term):
        return any(occurs(var, a) for a in t.args)
    if isinstance(t, Call):
        return any(occurs(var, a) for a in t.args)
    if isinstance(t, tuple):
        return any(occurs(var, a) for a in t)
    return False

def occurences(t, result):
    if isinstance(t, Variable):
        result.add(t)
    if isinstance(t, Term):
        for a in t.args:
            occurences(a, result)
    if isinstance(t, Call):
        for a in t.args:
            occurences(a, result)
    if isinstance(t, tuple):
        for a in t:
            occurences(a, result)
    return result

def step(t, subs):
    while isinstance(t, Variable) and t in subs:
        t = subs[t]
    return t

def walk(t, subs):
    t = step(t, subs)
    if isinstance(t, Term):
        args = tuple(walk(a, subs) for a in t.args)
        return Term(t.functor, args)
    if isinstance(t, Call):
        args = tuple(walk(a, subs) for a in t.args)
        return Call(t.func, args)
    if isinstance(t, tuple):
        return tuple(walk(a, subs) for a in t)
    return t

def evaluate(t, subs):
    t = step(t, subs)
    if isinstance(t, Term):
        args = tuple(evaluate(a, subs) for a in t.args)
        return Term(t.functor, args)
    if isinstance(t, Call):
        args = tuple(evaluate(a, subs) for a in t.args)
        return t.func(*args)
    if isinstance(t, tuple):
        return tuple(evaluate(a, subs) for a in t)
    return t

def recall(t, ren):
    if isinstance(t, Term) and t.functor in ren:
        args = tuple(recall(a, ren) for a in t.args)
        return Call(ren[t.functor], args)
    elif isinstance(t, Term):
        args = tuple(recall(a, ren) for a in t.args)
        return Term(t.functor, args)
    if isinstance(t, Call):
        args = tuple(recall(a, ren) for a in t.args)
        return Call(t.func, args)
    if isinstance(t, tuple):
        return tuple(recall(a, ren) for a in t)
    return t

def is_ground(t):
    if isinstance(t, Variable):
        return False
    if isinstance(t, Call):
        return False
    if isinstance(t, Term):
        return all(is_ground(a) for a in t.args)
    if isinstance(t, tuple):
        return all(is_ground(a) for a in t)
    return True

def is_evaluable(t):
    if isinstance(t, Variable):
        return False
    if isinstance(t, Call):
        return all(is_evaluable(a) for a in t.args)
    if isinstance(t, Term):
        return all(is_evaluable(a) for a in t.args)
    if isinstance(t, tuple):
        return all(is_evaluable(a) for a in t)
    return True

def build_groups(rules, graph):
    for rule in rules:
        name, depends_on = rule[3]()
        try:
            graph[name].update(depends_on)
        except KeyError:
            graph[name] = set(depends_on)
    index = 0
    stack = []
    v = {name:[None, None, False] for name in graph}
    scc = []
    def strongconnect(name):
        nonlocal index
        v[name][0] = index
        v[name][1] = index
        index += 1
        stack.append(name)
        v[name][2] = True
        for other in graph[name]:
            if other in v:
                if v[other][0] is None:
                    strongconnect(other)
                    v[name][1] = min(v[name][1], v[other][1])
                elif v[other][2]:
                    v[name][1] = min(v[name][1], v[other][0])
        if v[name][1] == v[name][0]:
            out = []
            w = stack.pop()
            v[w][2] = False
            out.append(w)
            while w != name:
                w = stack.pop()
                v[w][2] = False
                out.append[w]
            scc.append(out)
    for name in graph:
        if v[name][0] is None:
            strongconnect(name)
    groups = []
    for names in scc:
        group = []
        for rule in rules:
            if rule[3]()[0] in names:
                group.append(rule)
        groups.append((names, group))
    return groups

class Store:
    def __init__(self, data):
        self.data = data

X = Variable('X')
Y = Variable('Y')
Z = Variable('Z')

def window(group, order, aggregations):
    def _chain_(cb):
        def _init_(store):
            return cb[0](store)
        def _rerun_(pivot):
            return cb[1](pivot)
        def _impl_(psubs, pivot, work, store, new, era, cn):
            partition = tuple(o for o in _occur_(set()) if o not in group)
            occ = cb[4](set())
            partitions = dict()
            for psub in psubs:
                key = evaluate(partition, psub)
                partitions.setdefault(key, list()).append(psub)
            def sort_key(psub):
                return evaluate(order, psub)
            nsubs = set()
            for _, ppsubs in partitions.items():
                if order is not None:
                    ppsubs.sort(key = sort_key)
                ag = []
                rankvar = None
                for var, func, params in aggregations:
                    if func == 'max':
                        ag.append((var, max(evaluate(params[0], psub) for psub in ppsubs)))
                    elif func == 'min':
                        ag.append((var, min(evaluate(params[0], psub) for psub in ppsubs)))
                    elif func == 'sum':
                        ag.append((var, sum(evaluate(params[0], psub) for psub in ppsubs)))
                    elif func == 'avg':
                        ag.append((var, sum(evaluate(params[0], psub) for psub in ppsubs) / len(ppsubs)))
                    elif func == 'count':
                        ag.append((var, len(ppsubs)))
                    elif func == 'rank':
                        rankvar = var
                    else:
                        assert False, f"unknown aggregate function {func}"
                for i, psub in enumerate(ppsubs):
                    if rankvar is not None:
                        psub = unify(i, evaluate(rankvar, psub), psub)
                    for var, value in ag:
                        if psub is not None:
                            psub = unify(evaluate(var, psub), value, psub)
                    if psub is None:
                        continue
                    nsubs.add(prune(psub, occ))
            if nsubs:
                cb[2](nsubs, pivot, work, store, new, era, cn)
        def _graph_():
            return cb[3]()
        def _occur_(result):
            occurences(group, result)
            occurences(order, result)
            for k, func, params in aggregations:
                occurences(k, result)
                occurences(params, result)
            return cb[4](result)
        return _init_, _rerun_, _impl_, _graph_, _occur_
    return _chain_

def query(name, *params):
    def _chain_(cb):
        def _init_(store):
            return cb[0](store)
        def _rerun_(pivot):
            return cb[1](pivot) or name == pivot
        def _impl_(psubs, pivot, work, store, new, era, cn):
            occ = cb[4](set())
            try:
                seq = work if name == pivot else store.data[name]
            except KeyError:
                seq = set()
            nsubs = set()
            for psub in psubs:
                head = evaluate(Term(name, params), psub)
                for t in seq:
                    subs = unify(head, Term(name, t), psub)
                    if subs is not None:
                        nsubs.add(prune(subs, occ))
            if nsubs:
                cb[2](nsubs, pivot, work, store, new, era, cn)
        def _graph_():
            dst, src = cb[3]()
            return dst, src + [name]
        def _occur_(result):
            occurences(Term(name, params), result)
            return cb[4](result)
        return _init_, _rerun_, _impl_, _graph_, _occur_
    return _chain_

def prune(subs, occ):
    return Map({k:v for k,v in subs.items() if k in occ})

def check(param):
    def _chain_(cb):
        def _init_(store):
            return cb[0](store)
        def _rerun_(pivot):
            return cb[1](pivot)
        def _impl_(psubs, pivot, work, store, new, era, cn):
            nsubs = set()
            for psub in psubs:
                if evaluate(param, psub):
                    nsubs.add(psub)
            if nsubs:
                cb[2](nsubs, pivot, work, store, new, era, cn)
        def _graph_():
            return cb[3]()
        def _occur_(result):
            occurences(param, result)
            return cb[4](result)
        return _init_, _rerun_, _impl_, _graph_, _occur_
    return _chain_

def insert(name, *params):
    def _init_(store):
        if name not in store.data:
            store.data[name] = set()
    def _rerun_(pivot):
        return False
    def _impl_(psubs, pivot, work, store, new, era, cn):
        for psub in psubs:
            t = tuple(evaluate(p, psub) for p in params)
            assert is_ground(Term(name, t))
            if t not in store.data[name]:
                new.setdefault(name, set()).add(t)
    def _graph_():
        return name, []
    def _occur_(result):
        for param in params:
            occurences(param, result)
        return result
    return _init_, _rerun_, _impl_, _graph_, _occur_

def mutate(inserts, deletions):
    def _init_(store):
        for ins in inserts:
            name = ins.functor
            if name not in store.data:
                store.data[name] = set()
    def _rerun_(pivot):
        return False
    def _impl_(psubs, pivot, work, store, new, era, cn):
        for psub in psubs:
            for ins in inserts:
                ins = evaluate(ins, psub)
                assert is_ground(ins)
                name, t = ins
                if name not in new:
                    new[name] = set([t])
                else:
                    new[name].add(t)
            for de in deletions:
                de = evaluate(de, psub)
                assert is_ground(de)
                name, t = de
                if name not in era:
                    era[name] = set([t])
                else:
                    era[name].add(t)
    def _graph_():
        return '', []
    def _occur_(result):
        for ins in inserts:
            occurences(ins, result)
        for de in deletions:
            occurences(de, result)
        return result
    return _init_, _rerun_, _impl_, _graph_, _occur_

def constraint(name, param):
    def _init_(store):
        if name not in store.data:
            store.data[name] = set()
    def _rerun_(pivot):
        return False
    def _impl_(psubs, pivot, work, store, new, era, cn):
        for psub in psubs:
            p = walk(param, psub)
            assert is_evaluable(p)
            cn.setdefault(name, []).append(p)
    def _graph_():
        return name, []
    def _occur_(result):
        return occurences(param, result)
    return _init_, _rerun_, _impl_, _graph_, _occur_

def rule(head, *chain):
    for fn in reversed(chain):
        head = fn(head)
    return head

n = 0
def run(store, rules, once=False):
    global n
    empty = Map()
    new = dict()
    era = dict()
    cn  = dict()
    for rule in rules:
        rule[0](store)
    for rule in rules:
        rule[2]([empty], None, None, store, new, era, cn)
    while new and not once:
        n += 1
        fresh, new = new, dict()
        for name in era:
            store.data[name].difference_update(era[name])
        for name in fresh:
            store.data[name].update(fresh[name])
        era.clear()
        for name in fresh:
            for rule in rules:
                if rule[1](name):
                    rule[2]([empty], name, fresh[name], store, new, era, cn)
    if once:
        for name in era:
            store.data[name].difference_update(era[name])
        for name in new:
            store.data[name].update(new[name])
    return cn

def prepare_solver(t, mapping, fresh):
    if isinstance(t, Term):
        t = evaluate(t, {})
        if t in mapping:
            u = mapping[t]
        else:
            u = mapping[t] = fresh('_')
        return u
    if isinstance(t, Call):
        args = [prepare_solver(a, mapping, fresh) for a in t.args]
        return t.func(*args)
    if isinstance(t, tuple):
        return tuple(prepare_solver(a, mapping, fresh) for a in t)
    return t

def layout_solver(out, cs):
    def LRect(a):
        return LVariable(a), LVariable(a), LVariable(a), LVariable(a)
    solver = Solver()
    mapping = {}
    for c in cs:
        if isinstance(c, Term) and c.functor == 'area':
            rc, xs, ys = c.args
            rc = prepare_solver(rc, mapping, LRect)
            xs = prepare_solver(xs, mapping, LRect)
            ys = prepare_solver(ys, mapping, LRect)
            solver.addConstraint(rc[0] == xs[0])
            solver.addConstraint(rc[1] == ys[1])
            solver.addConstraint(rc[0] + rc[2] == xs[0] + xs[2])
            solver.addConstraint(rc[1] + rc[3] == ys[1] + ys[3])
        elif isinstance(c, Term) and c.functor == 'rows':
            rc, ss = c.args
            rc = prepare_solver(rc, mapping, LRect)
            ss = prepare_solver(ss, mapping, LRect)
            edge = rc[1] + rc[3]
            for s in ss:
                solver.addConstraint(s[0] == rc[0])
                solver.addConstraint(s[2] == rc[2])
                solver.addConstraint(s[1] + s[3] == edge)
                solver.addConstraint(s[3] >= 0)
                edge = s[1]
            solver.addConstraint(rc[1] == edge)
        elif isinstance(c, Term) and c.functor == 'cols':
            rc, ss = c.args
            rc = prepare_solver(rc, mapping, LRect)
            ss = prepare_solver(ss, mapping, LRect)
            edge = rc[0]
            for s in ss:
                solver.addConstraint(s[1] == rc[1])
                solver.addConstraint(s[3] == rc[3])
                solver.addConstraint(s[0] == edge)
                solver.addConstraint(s[2] >= 0)
                edge = s[0] + s[2]
            solver.addConstraint(rc[0] + rc[2] == edge)
        else:
            c = prepare_solver(c, mapping, LRect)
            solver.addConstraint(c)
    solver.updateVariables()
    for name in mapping:
        out.add((name, mapping[name].value()))

def var_solver(out, cs):
    solver = Solver()
    mapping = {}
    for c in cs:
        c = prepare_solver(c, mapping, LVariable)
        solver.addConstraint(c)
    solver.updateVariables()
    for name in mapping:
        out.add((name, mapping[name].value()))

def run_program(program, store, stages):
    rules, mutators, solvers = program
    graph = {n:deps for n, (_, deps) in stages.items()}
    groups = build_groups(rules, graph)
    for names, group_rules in groups:
        for stage_name in stages:
            if stage_name in names:
                assert all(dep not in names for dep in stages[stage_name][1]), \
                    f"Stage {stage_name} mixed with dependencies in SCC"
    for names, group_rules in groups:
        cn = run(store, group_rules)
        for name in cn:
            solve = solvers.get(name, var_solver)
            solve(store.data[name], cn[name])
        for stage_name in stages:
            if stage_name in names:
                stages[stage_name][0](store)
    run(store, mutators, once=True)

if __name__=='__main__':
    store = Store(dict(
    						edge = set([ (0,1), (1,0), (2,0), (2,1), (3,2), (3,1) ])))
    
    rules = [
    		rule(insert('edge', 5, 2)),
    		rule(insert('path', X, Y), query('edge', X, Y)),
    		rule(insert('path', X, Z), query('edge', X, Y), query('path', Y, Z)),
    		rule(insert('present', X), query('path', 5, X)),
    		rule(insert('oh', X), query('on', Term('click', ()), X)),
    		rule(constraint('var', Call(op.eq, [Term('x', ()), 5]))),
    		rule(constraint('var', Call(op.eq, [
    										Call(op.add, [Term('x', ()), Term('y', ())]), 8]))),
    ]
    mutators = [
    		rule(mutate([Term('edge', (7, 8))], [Term('edge', (3, 2))])),
    ]
    solvers = {}
    
    groups = build_groups(rules, {'on': ['present']})
    for names, rules in groups:
        assert not ('on' in names and 'present' in names)
    
    for names, rules in groups:
        cn = run(store, rules)
        for name in cn:
            solve = solvers.get(name, var_solver)
            solve(store.data[name], cn[name])
        if 'present' in names:
            store.data['on'] = set()
            for arg in store.data['present']:
                store.data['on'].add((Term('click', ()), arg))
    run(store, mutators)
    
    for name in store.data:
        for params in store.data[name]:
            print(Term(name, params))
