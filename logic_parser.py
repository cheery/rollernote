import ply.lex as lex
import ply.yacc as yacc
import logic as core
import logic_ast as ast
import logic_builder as builder

# List of token names
tokens = (
    'ATOM', 'VAR', 'INT', 'STRING', 
    'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE', 
    'BAR', 'COMMA', 'SEMICOLON', 'EQUALS',
    'PLUS', 'MINUS', 'TIMES', 'DIVIDE', 'MODULO',
    'LE', 'GE', 'LT', 'GT',
    'TILDE', 'QUESTION',
)

# Regular expressions for simple tokens
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_BAR = r'\|'
t_COMMA = r','
t_SEMICOLON = r';'
t_EQUALS = r'='
t_PLUS = r'\+'
t_MINUS = r'-'
t_TIMES = r'\*'
t_DIVIDE = r'/'
t_MODULO = r'%'
t_LE = r'<='
t_GE = r'>='
t_LT = r'<'
t_GT = r'>'
t_TILDE = r'~'
t_QUESTION = r'\?'

# Reserved keywords
reserved = {
    'data': 'DATA',
    'type': 'TYPE',
    'constraint': 'CONSTRAINT'
}

tokens += tuple(reserved.values())

# Regex for atoms (lowercase starting identifiers) and variables (uppercase)
def t_ATOM(t):
    r'[a-z][a-zA-Z0-9_]*'
    t.type = reserved.get(t.value, 'ATOM')  # Check for reserved words
    return t

def t_VAR(t):
    r'[A-Z][a-zA-Z0-9_]*'
    return t

# Integers and strings
def t_INT(t):
    r'\d+'
    t.value = int(t.value)
    return t

def t_STRING(t):
    r'\".*?\"'
    t.value = t.value.strip('"')
    return t

# Ignoring spaces and tabs
t_ignore = ' \t'

# Newline handling
def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)

def t_comment(t):
    r'\#.*\n'
    t.lexer.lineno += 1

# Error handling
def t_error(t):
    print(f"Illegal character '{t.value[0]}'")
    t.lexer.skip(1)

# Precedence and associativity of operators
precedence = (
    ('right', 'SEMICOLON'),
    ('right', 'COMMA'),
    ('left', 'EQUALS'),
    ('left', 'LE', 'GE', 'LT', 'GT'),
    ('left', 'PLUS', 'MINUS'),
    ('left', 'TIMES', 'DIVIDE', 'MODULO')
)

# Grammar rules

def p_program(p):
    '''program : declarations'''
    p[0] = ast.Program(p[1])

def p_declarations(p):
    '''declarations : declaration
                    | declaration declarations'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[2]

def p_declaration(p):
    '''declaration : data_declaration
                   | type_declaration
                   | rule_declaration
                   | constraint_declaration
                   | query '''
    p[0] = p[1]

# Datatype declaration
def p_data_declaration(p):
    '''data_declaration : DATA VAR LBRACE constructors RBRACE'''
    p[0] = ast.DataDeclaration(p[2], p[4], p.lineno(1))

def p_constructors(p):
    '''constructors : constructor
                    | constructor BAR constructors'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]

def p_constructor(p):
    '''constructor : ATOM LPAREN vars RPAREN
                   | ATOM'''
    if len(p) == 2:
        p[0] = (p[1], [])
    else:
        p[0] = (p[1], p[3])

def p_params(p):
    '''params : expr
              | expr COMMA params
       vars : VAR
            | VAR COMMA vars'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]

def p_term(p):
    '''term : ATOM
            | VAR
            | ATOM LPAREN params RPAREN'''
    if len(p) == 2:
        if p[1][0].isupper():
            p[0] = ast.Variable(p[1])
        else:
            p[0] = ast.Term(p[1], [])
    else:
        p[0] = ast.Term(p[1], p[3])

# Type declaration
def p_type_declaration(p):
    '''type_declaration : TYPE ATOM LPAREN vars RPAREN'''
    p[0] = ast.TypeDeclaration(p[2], p[4], p.lineno(1))

# Rule declaration
def p_rule_declaration(p):
    '''rule_declaration : ATOM LPAREN params RPAREN LBRACE goals RBRACE
                        | ATOM LBRACE goals RBRACE'''
    if len(p) == 8:
        p[0] = ast.RuleDeclaration(p[1], p[3], p[6], p.lineno(1))
    else:
        p[0] = ast.RuleDeclaration(p[1], [], p[3], p.lineno(1))

# Constraint declaration
def p_constraint_declaration(p):
    '''constraint_declaration : CONSTRAINT ATOM LPAREN vars RPAREN
                              | CONSTRAINT ATOM
                              | heads BAR guards LBRACE goals RBRACE
                              | heads LBRACE goals RBRACE'''
    if len(p) == 6:
        p[0] = ast.ConstraintDeclaration(p[2], p[4], p.lineno(1))
    elif len(p) == 2:
        p[0] = ast.ConstraintDeclaration(p[2], [], p.lineno(1))
    elif len(p) == 7:
        p[0] = ast.CHRDeclaration(p[1], p[3], p[5], p.lineno(4))
    else:
        p[0] = ast.CHRDeclaration(p[1], [], p[3], p.lineno(2))

def p_heads(p):
    '''heads : head
             | head COMMA heads'''
    if len(p) == 4:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = p[1]

def p_head(p):
    '''head : ATOM
            | TILDE ATOM
            | ATOM LPAREN params RPAREN
            | TILDE ATOM LPAREN params RPAREN'''
    if len(p) == 2:
        p[0] = False, p[1], []
    elif len(p) == 3:
        p[0] = True, p[2], []
    elif len(p) == 5:
        p[0] = False, p[1], p[3]
    else:
        p[0] = True, p[2], p[4]

# Guards and goals
def p_guards(p):
    '''guards : guard
              | guard COMMA guards'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]

def p_goals(p):
    '''goals :
             | goal'''
    if len(p) == 1:
        p[0] = ast.Invoke('true', [])
    else:
        p[0] = p[1]

# Goal types
def p_goal(p):
    '''goal : expr EQUALS expr
            | ATOM
            | ATOM LPAREN params RPAREN
            | LBRACE goals RBRACE
            | goal COMMA goal
            | goal SEMICOLON goal'''
    if len(p) == 4 and p[2] == '=':
        p[0] = ast.Unify(p[1], p[3])
    elif len(p) == 2:
        p[0] = ast.Invoke(p[1], [])
    elif len(p) == 5:
        p[0] = ast.Invoke(p[1], p[3])
    elif len(p) == 4 and p[1] == '{':
        p[0] = p[2]
    elif len(p) == 4 and p[2] == ',':
        p[0] = ast.Conj(p[1], p[3])
    else:
        p[0] = ast.Disj(p[1], p[3])

def p_guard(p):
    '''guard : expr LE expr
             | expr GE expr
             | expr LT expr
             | expr GT expr
             | expr EQUALS expr'''
    p[0] = p[2], p[1], p[3]

# Expressions (arithmetic, comparisons)
def p_expr(p):
    '''expr : int_literal
            | term
            | string_literal
            | expr PLUS expr
            | expr MINUS expr
            | expr TIMES expr
            | expr DIVIDE expr
            | expr MODULO expr'''
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = ast.Term(p[2], [p[1], p[3]])

def p_int_literal(p):
    '''int_literal : INT'''
    p[0] = ast.IntLiteral(p[1])

def p_string_literal(p):
    '''string_literal : STRING'''
    p[0] = ast.StringLiteral(p[1])

def p_query(p):
    '''query : QUESTION goal'''
    p[0] = ast.Query(p[2], p.lineno(1))

# Error handling
def p_error(p):
    if p is None:
        print(f"Syntax error at EOF")
    else:
        print(f"{p.lineno}: Syntax error at {repr(p.value)}")

# Build the lexer and parser
lexer = lex.lex()
parser = yacc.yacc(debug=False)

# Test input for parser (extended example)
input_str = '''
# CHRs
# constraint vs. rule
# type checking
# simple types
# parametric types

constraint foo(Int)
type append(List, List, List)

data List { nil | cons(Int, List) }

append(nil, X, X) {}
append(cons(H, T), L2, cons(H, L3)) { append(T, L2, L3) }

#data Thing { foo(Uid, Fractional, String) | bar | guux(Int) }
#type rule(Int, Uid, String)
#rule(X, Y, Z) { X = 1, foo(X, Y); guux; bar(Z+5) }
#goal {}
#constraint foo(Int, Thing)
#~foo(X, bar(Y)) | X > 5 { goal }
? append(X, Y, cons(0, cons(1, nil)))
'''

# Parse the input
result = parser.parse(input_str)
bd = builder.Builder({}, {}, {}, [], None)
for decl in result.declarations:
    decl.register(bd)

print(bd.datadecls)
print(bd.typedecls)
print(bd.chrd)

fnf = {
    '+': core.FnF('+', core.operator.add),
    '-': core.FnF('-', core.operator.sub),
    '/': core.FnF('/', core.operator.truediv),
    '*': core.FnF('*', core.operator.mul),
    '%': core.FnF('%', core.operator.mod),
}

module = {}

for sig, decls in bd.rules.items():
    def build(decls):
        for decl in decls:
            env = list(set(decl.variables()))
            env.sort()
            code = [core.Fresh(len(env))]
            for i, arg in enumerate(decl.args, len(env)):
                code.append(core.Unify(core.Ix(i), arg.as_core(env, fnf)))
            code.extend(decl.goal.construct(env, fnf))
            code.append(core.Success())
            yield code
    total = None
    for code in reversed(list(build(decls))):
        if total is None:
            total = code
        else:
            total = [core.Choice(len(code))] + code + total
    module[sig] = total

if bd.query is not None:
    env = list(set(bd.query.goal.variables()))
    env.sort()
    code = bd.query.goal.construct(env, fnf)
    code.append(core.Success())
    venv = [core.Variable() for _ in env]

    stream = core.Stream(module, [], core.init_frame(venv, code))
    names = dict(zip(env, venv))
    for subs, chrs in core.run(stream):
        show = core.Show(subs, names)
        print('result:')
        for name, var in names.items():
            print(f"  {name} = {show(var)}")
        for c in chrs:
            print("  " + c.show(show))
