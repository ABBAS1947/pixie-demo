"""Exact numeric parsing and verification of a deliberately bounded question grammar.

This verifies arithmetic, not skill mastery, content approval or independence.
Unsupported constructs return None; malformed answers abstain.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re

def parse_numeric(raw: str) -> Fraction | None:
    if not isinstance(raw, str) or len(raw) > 500: return None
    text=raw.strip().replace('\u2212','-')
    parts=re.fullmatch(r'([+-]?\d+)\s*/\s*([+-]?\d+)',text)
    if parts:
        try:return Fraction(int(parts[1]),int(parts[2]))
        except (ValueError,ZeroDivisionError):return None
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',text):return None
    try:
        value=Decimal(text)
        if not value.is_finite() or abs(value.as_tuple().exponent)>500:return None
        return Fraction(value)
    except (InvalidOperation,ValueError,OverflowError):return None

_OPERAND=r'(?:[+-]?\d+\s*/\s*[+-]?\d+|[+-]?(?:\d+(?:\.\d*)?|\.\d+))'
_QUESTION=re.compile(rf'^(?:what is|calculate|compute|evaluate)\s+({_OPERAND})\s*(plus|minus|times|multiplied by|divided by|\+|-|\*|\u00d7|\u00f7)\s*({_OPERAND})\s*[?.]?$',re.I)

def verify_arithmetic_question(question: str, response: str) -> str | None:
    if len(question)>200:return None
    match=_QUESTION.fullmatch(question.strip().replace('\u2212','-'))
    if not match:return None
    left,right=parse_numeric(match[1]),parse_numeric(match[3])
    if left is None or right is None:return None
    operator=match[2].lower()
    if operator in ('plus','+'):expected=left+right
    elif operator in ('minus','-'):expected=left-right
    elif operator in ('times','multiplied by','*','\u00d7'):expected=left*right
    else:
        if not right:return None
        expected=left/right
    answer=parse_numeric(response)
    if answer is None:return 'unassessable'
    return 'correct' if answer==expected else 'incorrect'
