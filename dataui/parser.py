import ply.lex as lex
import ply.yacc as yacc
from . import evaluator
import operator

tokens = (
    'NAME', 'VAR', 'INT', 'STRING',
    'LPAREN', 'RPAREN', 'COMMA', 'DOT',
    'LBRACKET', 'RBRACKET',
    'LBRACE', 'RBRACE',
    'IMPLIED_BY',
    'STAR', 'SLASH', 'MODULO', 'PSLASH',
    'QUESTION',
    'PLUS',
    'MINUS',
    'NE', 'EQ', 'LE', 'GE', 'LT', 'GT',
    'AT',
)

# Regular expressions for simple tokens
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
# t_BAR = r'\|'
t_COMMA = r','
t_DOT = r'\.'
t_IMPLIED_BY = r':-'
t_STAR = r'\*'
t_SLASH = r'/'
t_PSLASH = r':/:'
t_MODULO = r'%'
t_QUESTION = r'\?'
#t_EQUALS = r'='
t_PLUS = r'\+'
t_MINUS = r'-'
t_NE = r'!='
t_EQ = r'=='
t_LE = r'<='
t_GE = r'>='
t_LT = r'<'
t_GT = r'>'
# t_TILDE = r'~'
t_AT = r'@'
# t_FUNC_ARROW = r'=>'
# t_ARROW = r'->'

# Reserved keywords
reserved = {
}
tokens += tuple(set(reserved.values()))

def t_NAME(t):
    r'[a-zA-Z_][a-zA-Z0-9_]*'
    t.type = reserved.get(t.value, 'NAME')  # Check for reserved words
    if t.value.istitle():
        t.type = 'VAR'
    return t

def t_INT(t):
    r'\d+'
    t.value = int(t.value)
    return t

def t_STRING(t):
    r'\".*?\"'
    t.value = t.value.strip('"')
    return t

t_ignore = ' \t'

def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)

def t_comment(t):
    r'\#.*\n'
    t.lexer.lineno += 1

def t_error(t):
    print(f"Illegal character '{t.value[0]}'")
    t.lexer.skip(1)

precedence = (
     ('left', 'LE', 'GE', 'LT', 'GT', 'EQ', 'NE'),
     ('left', 'PLUS', 'MINUS'),
     ('left', 'STAR', 'SLASH', 'MODULO')
)

def p_program(p):
    '''program : declarations'''
    p[0] = p[1]

def p_declarations_0(p):
    '''declarations : declaration'''
    p[0] = [p[1]]

def p_declarations_1(p):
    '''declarations : declaration declarations'''
    p[0] = [p[1]] + p[2]

def p_declaration_0(p):
    '''declaration : expr DOT'''
    p[0] = 'rule', p[1], []

def p_declaration_1(p):
    '''declaration : expr IMPLIED_BY exprs_comma DOT'''
    p[0] = 'rule', p[1], p[3]

def p_declaration_2_0(p):
    '''declaration : exprs PSLASH q_exprs DOT'''
    p[0] = 'delta', p[1], p[3], []

def p_declaration_2(p):
    '''declaration : exprs PSLASH q_exprs IMPLIED_BY exprs_comma DOT'''
    p[0] = 'delta', p[1], p[3], p[5]

def p_declaration_3(p):
    '''declaration : NAME LBRACE expr RBRACE DOT'''
    p[0] = 'constraint', p[1], p[3], []

def p_declaration_4(p):
    '''declaration : NAME LBRACE expr RBRACE IMPLIED_BY exprs_comma DOT'''
    p[0] = 'constraint', p[1], p[3], p[6]

def p_declaration_5(p):
    '''declaration : AT NAME NAME DOT'''
    p[0] = 'solver', p[2], p[3]

def p_terms_0(p):
    '''terms : '''
    p[0] = []

def p_terms_1(p):
    '''terms : term terms'''
    p[0] = [p[1]] + p[2]

def p_term_0(p):
    '''term : NAME'''
    p[0] = evaluator.Term(p[1], ())

def p_term_1(p):
    '''term : LPAREN expr RPAREN'''
    p[0] = p[2]

def p_exprs_0(p):
    '''exprs : '''
    p[0] = []

def p_q_exprs_0(p):
    '''q_exprs : '''
    p[0] = []

def p_exprs_1(p):
    '''exprs : exprs_comma'''
    p[0] = p[1]

def p_q_exprs_1(p):
    '''q_exprs : q_exprs_comma'''
    p[0] = p[1]

def p_exprs_2(p):
    '''exprs_comma : expr'''
    p[0] = [p[1]]

def p_q_exprs_2(p):
    '''q_exprs_comma : q_expr'''
    p[0] = [p[1]]

def p_exprs_3(p):
    '''exprs_comma : expr COMMA exprs_comma'''
    p[0] = [p[1]] + p[3]

def p_q_exprs_3(p):
    '''q_exprs_comma : q_expr COMMA q_exprs_comma'''
    p[0] = [p[1]] + p[3]

def p_q_expr(p):
    '''q_expr : QUESTION expr
              | expr'''
    p[0] = (len(p) == 3), (p[1] if len(p) == 2 else p[2])

def p_expr_0(p):
    '''expr : NAME terms'''
    p[0] = evaluator.Term(p[1], p[2])

def p_expr_1(p):
    '''expr : literal'''
    p[0] = p[1]

def p_expr_2(p):
    '''expr : expr PLUS expr
            | expr MINUS expr
            | expr EQ expr
            | expr NE expr
            | expr LE expr
            | expr GE expr
            | expr LT expr
            | expr GT expr
            | expr STAR expr
            | expr SLASH expr
            | expr MODULO expr'''
    op = {
        '+': operator.add, '-': operator.sub,
        '==': operator.eq, '!=': operator.ne,
        '<=': operator.le, '>=': operator.ge,
        '<': operator.lt, '>': operator.gt,
        '*': operator.mul, '/': operator.truediv,
        '%': operator.mod}[p[2]]
    p[0] = evaluator.Call(op, [p[1], p[3]])

def p_expr_3(p):
    '''expr : MINUS expr'''
    p[0] = evaluator.Call(operator.neg, [p[2]])

def p_term_2(p):
    '''term : LBRACKET exprs RBRACKET'''
    p[0] = tuple(p[2])

def p_term_3(p):
    '''term : literal'''
    p[0] = p[1]

def p_literal_0(p):
    '''literal : INT'''
    p[0] = int(p[1])

def p_literal_1(p):
    '''literal : STRING'''
    p[0] = int(p[1])

def p_literal_2(p):
    '''literal : VAR'''
    p[0] = evaluator.Variable(p[1])

def p_error(p):
    if p is None:
        print(f"Syntax error at EOF")
    else:
        print(f"{p.lineno}: Syntax error at {repr(p.value)}")
 
lexer = lex.lex()
parser = yacc.yacc(debug=True)

def parse(string):
    result = parser.parse(string)
    if result is None:
        return None

    renamings = {
        'repr': repr,
        'left': evaluator.left,
        'bottom': evaluator.bottom,
        'right': evaluator.right,
        'top': evaluator.top,
        'xcenter': evaluator.xcenter,
        'ycenter': evaluator.ycenter,
        'width': evaluator.width,
        'height': evaluator.height,
    }
    available_solvers = {
        'var': evaluator.var_solver,
        'layout': evaluator.layout_solver,
    }

    rules = []
    mutators = []
    solvers = {}

    for row in result:
        name = row[0]
        if name == 'rule':
            name, head, body = row
            head = evaluator.recall(head, renamings)
            body = [evaluator.recall(p, renamings) for p in body]
            assert isinstance(head, evaluator.Term)
            block = [evaluator.insert(head.functor, *head.args)]
            for p in body:
                if isinstance(p, evaluator.Term):
                    s = evaluator.query(p.functor, *p.args)
                else:
                    s = evaluator.check(p)
                block.append(s)
            rules.append(evaluator.rule(*block))
        elif name == 'solver':
            name, solver, rule = row
            solvers[rule] = available_solvers[solver]
        elif name == 'constraint':
            name, functor, const, body = row
            const = evaluator.recall(const, renamings)
            body = [evaluator.recall(p, renamings) for p in body]
            block = [evaluator.constraint(functor, const)]
            for p in body:
                if isinstance(p, evaluator.Term):
                    s = evaluator.query(p.functor, *p.args)
                else:
                    s = evaluator.check(p)
                block.append(s)
            rules.append(evaluator.rule(*block))
        elif name == 'delta':
            name, ins, des, body = row
            ins = [evaluator.recall(p, renamings) for p in ins]
            des = [(b, evaluator.recall(p, renamings)) for b, p in des]
            body = [evaluator.recall(p, renamings) for p in body]
            block = [
                evaluator.mutate(ins, [p for b,p in des])
            ]
            for b,p in des:
                if not b:
                    block.append(evaluator.query(p.functor, *p.args))
            for p in body:
                if isinstance(p, evaluator.Term):
                    s = evaluator.query(p.functor, *p.args)
                else:
                    s = evaluator.check(p)
                block.append(s)
            mutators.append(evaluator.rule(*block))
        else:
            assert False, row
    return rules, mutators, solvers

if __name__=='__main__':
    with open('counter.ui', 'r') as fd:
        string = fd.read()

    program = parse(string)
    store = evaluator.Store(dict())

    def on_func(store):
        store.data.setdefault('on', set())
        for arg in store.data['present']:
            store.data['on'].add((evaluator.Term('click', ()), arg))
    stages = {
        'on': (on_func, ['present', 'button']),
    }
    evaluator.run_program(program, store, stages)
    
    for name in store.data:
        for params in store.data[name]:
            print(evaluator.Term(name, params))
