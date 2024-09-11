import regex
import ruamel.yaml as yaml
import ply.lex as lex
import ply.yacc as yacc

YaccError = yacc.YaccError

# TOKENS

reserved = {
    'true':     'TRUE'
    , 'false':  'FALSE'
    , 'yes':    'YES'
    , 'no':     'NO'
    , 'null':   'NULL'
    , 'and':    'AND'
    , 'or':     'OR'
    , 'not':    'NOT'
    , 'in':     'IN'
    , 'if':     'IF'
    , 'else':   'ELSE'
}

# List of token names.   This is always required
tokens = [
    'SPACE'
    , 'IDENTIFIER'
    , 'NUMBER'
    , 'STRING'
    , 'PLUS'
    , 'MINUS'
    , 'TIMES'
    , 'DIVIDE'
    , 'PERCENT'
    , 'LSHIFT'
    , 'RSHIFT'
    , 'LPAREN'
    , 'RPAREN'
    , 'LBRACKET'
    , 'RBRACKET'
    , 'LBRACE'
    , 'RBRACE'
    , 'DOLLAR'
    , 'DOT'
    , 'COLON'
    , 'COMMA'
    , 'QMARK'
    , 'LESS'
    , 'GREATER'
    , 'EQUAL'
    , 'NEQUAL'
    , 'LEQUAL'
    , 'GEQUAL'
    , 'HAT'
    , 'TILDE'
    , 'AMPERSAND'
    , 'SEPARATOR'
    , 'NUMBER_AND_EXPONENT'
    , 'UNKNOWN'
] + list(reserved.values())

# Regular expression rules for simple tokens
t_PLUS                  = r'\+'
t_MINUS                 = r'-'
t_TIMES                 = r'\*'
t_DIVIDE                = r'/'
t_PERCENT               = r'%'
t_LSHIFT                = r'<<'
t_RSHIFT                = r'>>'
t_LPAREN                = r'\('
t_RPAREN                = r'\)'
t_LBRACKET              = r'\['
t_RBRACKET              = r'\]'
t_LBRACE                = r'\{'
t_RBRACE                = r'\}'
t_DOLLAR                = r'\$'
t_DOT                   = r'\.'
t_COLON                 = r'\:'
t_COMMA                 = r','
t_QMARK                 = r'\?'
t_LESS                  = r'<'
t_GREATER               = r'>'
t_EQUAL                 = r"=="
t_NEQUAL                = r"!="
t_LEQUAL                = r"<="
t_GEQUAL                = r">="
t_HAT                   = r"\^"
t_TILDE                 = r"\~"
t_AMPERSAND             = r"&"
t_SEPARATOR             = r"\|"
t_NUMBER                = r'[0-9]+\b'
t_NUMBER_AND_EXPONENT   = r"[0-9]*e[-+][0-9]+"

# Ignore comments
t_ignore_COMMENT        = r'\#[^\n]*'

# Regular expression rules with some action code
def t_IDENTIFIER(t):
    r'[a-zA-Z_$][a-zA-Z0-9_$]*'
    t.type = reserved.get(t.value,'IDENTIFIER') # Check for reserved words
    return t
def t_STRING(t):
    r'"([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\''
    t.value = eval(t.value)  # pylint: disable=eval-used
    return t
def t_SPACE(t):
    r'[ \t\n\r]+'
    t.lexer.lineno += t.value.count('\n') # track line numbers
    return t

# Error handling rule -> Create the "UNKNOWN" token
def t_error(t):
    t.type = 'UNKNOWN'
    return t


# RULES

def p_expression(p):
    "expression : space level0"
    p[0] = p[2]

def p_level0(p):
    "level0 : level1"
    p[0] = p[1]
def p_level0_or(p):
    "level0 : level1 IF space level1 ELSE space level0"
    value, condition, fallback = p[1], p[4], p[7]
    p[0] = lambda r: value(r) if condition(r) else fallback(r)

def p_level1(p):
    "level1 : level2"
    p[0] = p[1]
def p_level1_or(p):
    "level1 : level1 OR space level2"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) or right(r)

def p_level2(p):
    "level2 : level3"
    p[0] = p[1]
def p_level2_and(p):
    "level2 : level2 AND space level3"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) and right(r)

def p_level3(p):
    "level3 : level4"
    p[0] = p[1]
def p_level3_not(p):
    "level3 : NOT space level3"
    level3 = p[3]
    p[0] = lambda r: not level3(r)

def p_level4(p):
    "level4 : level5"
    p[0] = p[1]
def p_level4_in(p):
    "level4 : level5 IN space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) in right(r)
def p_level4_not_in(p):
    "level4 : level5 NOT space IN space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) in right(r)
def p_level4_equal(p):
    "level4 : level5 EQUAL space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) == right(r)
def p_level4_less(p):
    "level4 : level5 LESS space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) < right(r)
def p_level4_greater(p):
    "level4 : level5 GREATER space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) > right(r)
def p_level4_less_equal(p):
    "level4 : level5 LEQUAL space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) <= right(r)
def p_level4_greater_equal(p):
    "level4 : level5 GEQUAL space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) >= right(r)
def p_level4_not_equal(p):
    "level4 : level5 NEQUAL space level5"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) != right(r)

def p_level5(p):
    "level5 : level6"
    p[0] = p[1]
def p_level5_plus(p):
    "level5 : level5 SEPARATOR space level6"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) | right(r)

def p_level6(p):
    "level6 : level7"
    p[0] = p[1]
def p_level6_plus(p):
    "level6 : level6 HAT space level7"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) ^ right(r)

def p_level7(p):
    "level7 : level8"
    p[0] = p[1]
def p_level7_plus(p):
    "level7 : level7 AMPERSAND space level8"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) & right(r)

def p_level8(p):
    "level8 : level9"
    p[0] = p[1]
def p_level8_plus(p):
    "level8 : level8 LSHIFT space level9"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) << right(r)
def p_level8_minus(p):
    "level8 : level8 RSHIFT space level9"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) >> right(r)

def p_level9(p):
    "level9 : level10"
    p[0] = p[1]
def p_level9_plus(p):
    "level9 : level9 PLUS space level10"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) + right(r)
def p_level9_minus(p):
    "level9 : level9 MINUS space level10"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) - right(r)

def p_level10(p):
    "level10 : level11"
    p[0] = p[1]
def p_level10_times(p):
    "level10 : level10 TIMES space level11"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) * right(r)
def p_level10_divides(p):
    "level10 : level10 DIVIDE space level11"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) / right(r)
def p_level10_floor_divide(p):
    "level10 : level10 DIVIDE DIVIDE space level11"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) // right(r)
def p_level10_modulo(p):
    "level10 : level10 PERCENT space level11"
    left, right = p[1], p[4]
    p[0] = lambda r: left(r) % right(r)


def p_level11(p):
    "level11 : level12"
    p[0] = p[1]
def p_level11_minus(p):
    "level11 : MINUS space level12"
    level12 = p[3]
    p[0] = lambda r: -level12(r)
def p_level11_plus(p):
    "level11 : PLUS space level12"
    level12 = p[3]
    p[0] = lambda r: +level12(r)
def p_level11_bitwise_not(p):
    "level11 : TILDE space level12"
    level12 = p[3]
    p[0] = lambda r: ~level12(r)

def p_level12(p):
    "level12 : operand"
    p[0] = p[1]
def p_level12_exponentiation(p):
    "level12 : operand TIMES TIMES space operand"
    base, exponent = p[1], p[5]
    p[0] = lambda r: base(r) ** exponent(r)

def p_operand(p):
    """operand : number
               | variable"""
    p[0] = p[1]
def p_operand_string(p):
    "operand : STRING space"
    VALUE = p[1]
    p[0] = lambda _: VALUE
def p_operand_true(p):
    """operand : TRUE space
                | YES space"""
    p[0] = lambda _: True
def p_operand_false(p):
    """operand : FALSE space
                | NO space"""
    p[0] = lambda _: False
def p_operand_null(p):
    """operand : NULL space
                | TILDE space"""
    p[0] = lambda _: None
def p_operand_parenthesized(p):
    "operand : LPAREN space level0 space RPAREN"
    p[0] = p[3]
def p_operand_sequence(p):
    "operand : LBRACKET space sequence space RBRACKET"
    p[0] = p[3]
def p_operand_mapping(p):
    "operand : LBRACE space mapping space RBRACE"
    p[0] = p[3]

def p_number(p):
    """number : NUMBER space
                | DOT NUMBER space
                | DOT NUMBER_AND_EXPONENT space
                | NUMBER DOT NUMBER space
                | NUMBER DOT NUMBER_AND_EXPONENT space
    """
    NUMBER = eval("".join([t.value for t in p.slice[1:]]))  # pylint: disable=eval-used
    p[0] = lambda _: NUMBER
# Regex format for numbers
re_number = regex.compile(
    f"""^(    {t_NUMBER}
                | {t_DOT} {t_NUMBER}
                | {t_DOT} {t_NUMBER_AND_EXPONENT}
                | {t_NUMBER} {t_DOT} {t_NUMBER}
                | {t_NUMBER} {t_DOT} {t_NUMBER_AND_EXPONENT}
    )$"""
    .replace("\n", "")
    .replace("\t", "")
    .replace(" ", "")
)

def p_sequence_empty(p):
    "sequence : "
    p[0] = lambda _: ()
def p_sequence(p):
    "sequence : level0"
    level0 = p[1]
    p[0] = lambda r: (level0(r),)
def p_sequence_explode(p):
    "sequence : TIMES space level0"
    p[0] = p[3]
def p_sequence_recursion(p):
    "sequence : level0 COMMA space sequence"
    level0, sequence = p[1], p[4]
    p[0] = lambda r: (level0(r), *sequence(r))
def p_sequence_recursion_explode(p):
    "sequence : TIMES space level0 COMMA space sequence"
    level0, sequence = p[3], p[6]
    p[0] = lambda r: (*level0(r), *sequence(r))

def p_mapping_empty(p):
    "mapping : "
    p[0] = lambda _: {}
def p_mapping_normal(p):
    "mapping : key COLON SPACE level0"
    key, level0 = p[1], p[4]
    p[0] = lambda r: {key(r): level0(r)}
def p_mapping_null(p):
    """mapping : key COLON space
               | key"""
    key = p[1]
    p[0] = lambda r: {key(r): None}
def p_mapping_explode(p):
    "mapping : TIMES TIMES space level0"
    p[0] = p[4]
def p_mapping_recursion(p):
    "mapping : key COLON SPACE level0 COMMA space mapping"
    key, level0, mapping = p[1], p[5], p[6]
    p[0] = lambda r: {key(r): level0(r), **mapping(r)}
def p_mapping_recursion_null1(p):
    "mapping : key COLON space COMMA space mapping"
    key, mapping = p[1], p[6]
    p[0] = lambda r: {key(r): None, **mapping(r)}
def p_mapping_recursion_null2(p):
    "mapping : key COMMA space mapping"
    key, mapping = p[1], p[4]
    p[0] = lambda r: {key(r): None, **mapping(r)}
def p_mapping_recursion_explode(p):
    "mapping : TIMES TIMES space level0 COMMA space mapping"
    level0, mapping = p[4], p[7]
    p[0] = lambda r: {**level0(r), **mapping(r)}

def p_key(p):
    """key : generic_key
           | STRING space"""
    # Check, if the generic key matches number (we cannot match it with rules)
    if re_number.match(p[1]):
        NUMBER = eval(p[1])  # pylint: disable=eval-used
        p[0] = lambda _: NUMBER

    # Check if the key is one of the keywords
    elif p[1] in ['true', 'yes']:
        p[0] = lambda _: True
    elif p[1] in ['false', 'no']:
        p[0] = lambda _: False
    elif p[1] == 'null':
        p[0] = lambda _: None

    # Fallback to all tokens
    else:
        VALUE = p[1]
        p[0] = lambda _: VALUE
def p_key_expression(p):
    "key : LPAREN space level0 RPAREN space"
    p[0] = p[3]
def p_key_sequence(p):
    "key : LBRACKET space sequence RBRACKET space"
    p[0] = p[3]

def p_generic_key_start(p):
    "generic_key : non_colon_start"
    p[0] = p[1]
def p_generic_key_rest(p):
    "generic_key : generic_key non_colon_rest"
    p[0] = p[1] + p[2]
def p_generic_key_space_rest(p):
    "generic_key : generic_key SPACE non_colon_rest"
    p[0] = p[1] + p[2] + p[3]
def p_generic_key_colon_rest(p):
    "generic_key : generic_key COLON colons non_colon_rest"
    p[0] = p[1] + p[2] + p[3] + p[4]

def p_colons_empty(p):
    """colons : """
    p[0] = ""
def p_colons(p):
    """colons : COLON colons"""
    p[0] = p[1] + p[2]

def p_non_colon_start(p):
    """non_colon_start : IDENTIFIER
                       | NUMBER
                       | TRUE
                       | FALSE
                       | YES
                       | NO
                       | NULL
                       | AND
                       | OR
                       | NOT
                       | IN
                       | IF
                       | ELSE
                       | TILDE
                       | PLUS
                       | MINUS
                       | TIMES
                       | DIVIDE
                       | PERCENT
                       | RPAREN
                       | RBRACKET
                       | RBRACE
                       | DOLLAR
                       | DOT
                       | COMMA
                       | EQUAL
                       | NUMBER_AND_EXPONENT
                       | UNKNOWN"""
    p[0] = p[1]
def p_non_colon_rest(p):
    """non_colon_rest : non_colon_start
                        | LPAREN
                        | LBRACKET
                        | LBRACE
                        | QMARK
                        | LESS
                        | GREATER
                        | LSHIFT
                        | RSHIFT
                        | LEQUAL
                        | GEQUAL
                        | NEQUAL
                        | HAT
                        | AMPERSAND
                        | SEPARATOR"""
    p[0] = p[1]

def p_variable(p):
    "variable : path"
    path = p[1]
    p[0] = lambda r: path(r).data
def p_variable_path_dots(p):
    "variable : path dots"
    def callback(r):
        dots = p[2](r)
        while len(dots) > 1:
            dots = dots[1:]
            p[1] = p[1].pop()
        print("Not Implemented!")
        p[0] = p[1]
    p[0] = callback
def p_variable_colon(p):
    "variable : COLON space"
    p[0] = lambda r: r.call_root().data
def p_variable_colon_dot(p):
    "variable : COLON space DOT space"
    p[0] = lambda r: r.call_root()
    print("Not Implemented!")

def p_dots_dot(p):
    "dots : DOT space"
    p[0] = p[1]
def p_dots_dots(p):
    "dots : DOT space dots"
    p[0] = p[1] + p[2]

def p_path_element(p):
    "path : IDENTIFIER space"
    IDENTIFIER = p[1]
    p[0] = lambda r: r.indirect(IDENTIFIER)
def p_path_dots_element(p):
    "path : dots element"
    def callback(r):
        result = r
        for _ in p[1]:
            if new_result := result.pop():
                result = new_result
            else:
                break # TODO: Error here
        p[0] = result.indirect(p[2](r))
    p[0] = callback
def p_path_colon_element(p):
    "path : COLON space element"
    element = p[2]
    p[0] = lambda r: r.call_root().indirect(element(r))
def p_path_path_dots_element(p):
    "path : path dots element"
    path, element = p[1], p[3]
    def callback(r):
        nonlocal path
        path = path(r)
        for _ in p[2][1:]:
            path = path.pop()
        return path.indirect(element(r))
    p[0] = callback
def p_path_call_empty(p):
    "path : path LPAREN space RPAREN space"
    path = p[1]
    p[0] = lambda r: path(r).indirect("return")
def p_path_call(p):
    "path : call level0 RPAREN space"
    call, level0 = p[1], p[2]
    p[0] = lambda r: call(r).indirect(level0(r))

def p_call(p):
    "call : call level0 COMMA space"
    call, level0 = p[1], p[2]
    p[0] = lambda r: call(r).indirect(level0(r))
def p_call_first(p):
    "call : path LPAREN space"
    p[0] = p[1]

def p_element_number(p):
    "element : NUMBER space"
    NUMBER = eval(p[2])  # pylint: disable=eval-used
    p[0] = lambda _: NUMBER
def p_element_literal(p):
    """element : STRING space
               | IDENTIFIER space"""
    STRING_OR_IDENTIFIER = p[2]
    p[0] = lambda _: STRING_OR_IDENTIFIER
def p_element_expression(p):
    "element : LPAREN space level0 RPAREN space"
    p[0] = p[3]
def p_element_sequence(p):
    "element : LBRACKET space sequence RBRACKET space"
    p[0] = p[3]

def p_space_empty(p):
    "space : "
    p[0] = ""
def p_space(p):
    "space : SPACE space"
    p[0] = p[1] + p[2]

def p_error(p):
    if p:
        print("Syntax error at token", p.type)
        # Just discard the token and tell the parser it's okay.
        parser.errok()
    else:
        print("Syntax error at EOF")


# INTERFACE

lexer = lex.lex()  # Build the lexer
parser = yacc.yacc(debug=True)  # Build the parser

def parse(data, print_tokens=False):
    if print_tokens:
        lexer.input(data)
        while True:
            tok = lex.token()
            if not tok:
                break
            print(tok)
    return parser.parse(data)
