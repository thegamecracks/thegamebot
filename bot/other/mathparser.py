"""Parser for mathematic expressions.

Technical parser definition is unknown.

Available syntax:
    (): Parentheses
      :
    **: Exponentation
      :
     ~: Bitwise NOT
     -: Unary Minus
     +: Unary Plus
      :
     /: Division
    //: Floor division
     %: Modulo
     *: Multiplication
      :
     +: Addition
     -: Subtraction
      :
    <<: Left Shift
    >>: Right Shift
      :
     &: Bitwise AND
      :
     ^: Bitwise XOR
      :
     |: Bitwise OR

Inspired (but not directly viewed) by sbesada:
    https://github.com/sbesada/python.math.expression.parser.pymep

References used:
    https://en.wikipedia.org/wiki/LR_parser

Resources on converting infix to postfix:
    https://en.wikipedia.org/wiki/Reverse_Polish_notation
    https://en.wikipedia.org/wiki/Shunting-yard_algorithm
    https://scriptasylum.com/tutorials/infix_postfix/algorithms/
        infix-postfix/index.html
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from decimal import Decimal


class Token:
    __slots__ = ['op', 'op_type', 'op_name', 'precedence', 'associativity',
                 'operands']

    def __init__(
            self, op, op_type, op_name,
            precedence=None, associativity=None, operands=None):
        self.op = op
        self.op_type = op_type
        self.op_name = op_name
        self.precedence = precedence
        self.associativity = associativity
        self.operands = operands

    def __repr__(self):
        return '{}({!r}, {!r}, {!r}, {!r}, {!r}, {!r})'.format(
            self.__class__.__name__,
            self.op, self.op_type, self.op_name,
            self.precedence, self.associativity, self.operands
        )

    def __str__(self):
        return self.op

    def __eq__(self, other):
        if isinstance(other, str):
            return self.op == other
        elif isinstance(other, self.__class__):
            return hash(self) == hash(other)
        return NotImplemented

    def evaluate(self, *operands):
        def make_integer(operand, operator_name):
            if isinstance(operand, Decimal):
                if operand.as_integer_ratio()[1] == 1:
                    return int(operand)
                else:
                    raise TypeError(f'{operator_name} does not accept '
                                    f'non-integers ({operand})')
            else:
                raise TypeError(f'Expected operand {operand} to be of type '
                                'Decimal but is of type '
                                f'{operand.__class__.__name__}')

        mode = self.op_name

        if len(operands) != self.operands:
            raise ValueError(f'Expected {self.operands} operands for {mode}, '
                             f'received {len(operands)}')

        if mode == 'EXPONENTATION':
            return operands[0] ** operands[1]
        elif mode == 'E_NOTATION':
            return operands[0] * 10 ** operands[1]
        elif mode == 'BITWISE_NOT':
            a = make_integer(operands[0], 'Bitwise NOT')
            return ~a
        if mode == 'POSITIVE':
            return +operands[0]
        if mode == 'NEGATIVE':
            return -operands[0]
        if mode == 'MULTIPLICATION':
            return operands[0] * operands[1]
        if mode == 'DIVISION':
            return operands[0] / operands[1]
        if mode == 'FLOOR_DIVISION':
            return operands[0] // operands[1]
        if mode == 'MODULO':
            return operands[0] % operands[1]
        if mode == 'ADDITION':
            return operands[0] + operands[1]
        if mode == 'SUBTRACTION':
            return operands[0] - operands[1]
        if mode == 'LEFT_SHIFT':
            a = make_integer(operands[0], 'Left Shift')
            b = make_integer(operands[1], 'Left Shift')
            return a << b
        if mode == 'RIGHT_SHIFT':
            a = make_integer(operands[0], 'Right Shift')
            b = make_integer(operands[1], 'Right Shift')
            return a >> b
        if mode == 'BITWISE_AND':
            a = make_integer(operands[0], 'Bitwise AND')
            b = make_integer(operands[1], 'Bitwise AND')
            return a & b
        if mode == 'BITWISE_XOR':
            a = make_integer(operands[0], 'Bitwise XOR')
            b = make_integer(operands[1], 'Bitwise XOR')
            return a ^ b
        if mode == 'BITWISE_OR':
            a = make_integer(operands[0], 'Bitwise OR')
            b = make_integer(operands[1], 'Bitwise OR')
            return a | b


class Postfix(list):
    TOKEN_DIGITS = '0123456789'
    @classmethod
    def tokenize(cls, expr):
        # Delete spaces
        expr = expr.replace(' ', '')

        def get_token():
            token = None

            for i, s in enumerate(expr):
                read_ahead_1 = expr[i+1:i+2]  # char to the right
                read_ahead_2 = expr[i:i+2]    # s + char to the right
                if s in cls.TOKEN_DIGITS:
                    # Integer
                    if token is None:
                        token = Token(None, 'OPERAND', 'INTEGER')
                    if token.op_name not in ('INTEGER', 'DECIMAL'):
                        break
                elif s == '.':
                    # Decimal
                    if token is None:
                        token = Token(None, 'OPERAND', 'DECIMAL')
                    if token.op_name not in ('INTEGER', 'DECIMAL'):
                        break
                elif s == '(':
                    # Left Parenthesis
                    if token is None:
                        token = Token(None, None, 'LEFT_PARENTHESIS', 0)
                        i += 1
                    break
                elif s == ')':
                    # Right Parenthesis
                    if token is None:
                        token = Token(None, None, 'RIGHT_PARENTHESIS', 0)
                        i += 1
                    break
                elif read_ahead_2 == '**':
                    # Exponentation
                    if token is None:
                        token = Token(None, 'OPERATOR', 'EXPONENTATION',
                                      1, 'LEFT', 2)
                        i += 2
                    break
                elif s in ('e', 'E'):
                    # E notation
                    if token is None:
                        token = Token(None, 'OPERATOR', 'E_NOTATION',
                                      1, 'LEFT', 2)
                        i += 1
                    break
                elif s == '~':
                    # Bitwise NOT
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'BITWISE_NOT', 1, 'RIGHT', 1)
                        i += 1
                    break
                elif s == '*':
                    # Multiplication
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'MULTIPLICATION', 2, 'LEFT', 2)
                        i += 1
                    break
                elif s == '/':
                    # Division
                    if token is None:
                        i += 1
                        if read_ahead_1 == '/':
                            # Floor Division
                            i += 1
                            token = Token(
                                None, 'OPERATOR', 'FLOOR_DIVISION', 2, 'LEFT',
                                2)
                        else:
                            token = Token(
                                None, 'OPERATOR', 'DIVISION', 2, 'LEFT', 2)
                    break
                elif s == '%':
                    # Modulo
                    if token is None:
                        token = Token(None, 'OPERATOR', 'MODULO', 2, 'LEFT', 2)
                        i += 1
                    break
                elif s == '+':
                    if token is None:
                        if tokens and (
                                tokens[-1].op_type == 'OPERAND'
                                or tokens[-1].op_name == 'RIGHT_PARENTHESIS'
                                ):
                            # Addition
                            token = Token(None, 'OPERATOR', 'ADDITION',
                                          3, 'LEFT', 2)
                        else:
                            # Unary plus
                            token = Token(None, 'OPERATOR', 'POSITIVE',
                                          1, 'RIGHT', 1)
                        i += 1
                    break
                elif s == '-':
                    # Subtraction
                    if token is None:
                        if tokens and (
                                tokens[-1].op_type == 'OPERAND'
                                or tokens[-1].op_name == 'RIGHT_PARENTHESIS'
                                ):
                            # Subtraction
                            token = Token(None, 'OPERATOR', 'SUBTRACTION',
                                          3, 'LEFT', 2)
                        else:
                            # Unary minus
                            token = Token(None, 'OPERATOR', 'NEGATIVE',
                                          1, 'RIGHT', 1)
                        i += 1
                    break
                elif read_ahead_2 == '<<':
                    # Left Shift
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'LEFT_SHIFT', 4, 'LEFT', 2)
                        i += 2
                    break
                elif read_ahead_2 == '>>':
                    # Right Shift
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'RIGHT_SHIFT', 4, 'LEFT', 2)
                        i += 2
                    break
                elif s == '&':
                    # Bitwise AND
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'BITWISE_AND', 5, 'LEFT', 2)
                        i += 1
                    break
                elif s == '^':
                    # Bitwise XOR
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'BITWISE_XOR', 6, 'LEFT', 2)
                        i += 1
                    break
                elif s == '|':
                    # Bitwise OR
                    if token is None:
                        token = Token(
                            None, 'OPERATOR', 'BITWISE_OR', 7, 'LEFT', 2)
                        i += 1
                    break
                else:
                    raise SyntaxError(f'Undefined token {expr[:i+1]!r}')
            else:
                i += 1

            token.op = expr[:i]

            # Modify unary plus and minus operators to display
            # a different symbol
            if token.op_name == 'POSITIVE':
                token.op = '(+)'
            elif token.op_name == 'NEGATIVE':
                token.op = '(-)'

            return token, expr[i:]

        tokens = []

        while expr:
            token, expr = get_token()
            tokens.append(token)

        return tokens

    @classmethod
    def from_infix(cls, expr):
        """Convert an infix mathematical expression into a Postfix object.

        It is guaranteed that all numbers are Decimal objects and all
        other operators (including parentheses) are Token objects.

        """
        queue = []
        op_stack = []

        tokens = cls.tokenize(expr)
        i, end = 0, len(tokens)

        while i < end:
            token = tokens[i]

            if token.op_type == 'OPERAND':
                queue.append(Decimal(token.op))

            elif token == '(':
                look_back = tokens[i - 1]
                if i != 0 and (
                        look_back.op_type == 'OPERAND'
                        or look_back.op_name == 'RIGHT_PARENTHESIS'):
                    # Implicit multiplication
                    op_stack.append(
                        Token('*', 'OPERATOR', 'MULTIPLICATION', 3, 'LEFT', 2))
                op_stack.append(token)

            elif token == ')':
                while op_stack \
                        and op_stack[-1] != '(':
                    queue.append(op_stack.pop())
                if op_stack:
                    # Discard left parenthesis
                    op_stack.pop()
                else:
                    raise SyntaxError(f'Mismatched parenthesis in {expr!r}')

            elif token.op_type == 'OPERATOR':
                while op_stack \
                        and (
                            op_stack[-1].precedence < token.precedence
                            or op_stack[-1].precedence == token.precedence
                            and token.associativity == 'LEFT'
                        ) and op_stack[-1].op_name != 'LEFT_PARENTHESIS':
                    queue.append(op_stack.pop())
                op_stack.append(token)

            i += 1

        while op_stack:
            if op_stack[-1] == '(':
                raise SyntaxError(f'Mismatched parenthesis in {expr!r}')
            queue.append(op_stack.pop())

        return cls(queue), tokens

    def evaluate(self, debug_output=None):
        def dprint(*args, **kwargs):
            print(*args, **kwargs, file=debug_output)

        if len(self) == 0:
            return

        while len(self) > 1:
            # Find first operator
            for i, t in enumerate(self):
                if isinstance(t, Token):
                    break
            else:
                raise SyntaxError('Could not find an operator')
            # Get operands for operator based on operator's expected amount
            look_back_index = i - t.operands
            if look_back_index < 0:
                raise SyntaxError(
                    f'Expected {t.operands} operands for {t.op_name}, '
                    f'received {t.operands + look_back_index}')
            args = self[look_back_index:i]
            # Evaluate the operator with given operands
            result = t.evaluate(*args)
            # Replace used operands and operator with the result
            self[look_back_index:i + 1] = [result]

            if debug_output is not None:
                dprint(' '.join([str(t) for t in self]))

        return self[0]


def main():
    while True:
        expr = input(': ')
        postfix, tokens = Postfix.from_infix(expr)
        print('Parsed tokens:', ' '.join([str(t) for t in tokens]))
        print('Generated postfix:', ' '.join([str(t) for t in postfix]))
        print('Evaluates to:', postfix.evaluate())


if __name__ == '__main__':
    main()
