"""Bounded dimensional checks for source-backed hourly-pay expressions.

This checks algebraic units, not statutory rates or legal applicability. No eval,
source rewriting, benchmark IDs, learned answer templates or invented premises.
"""
import ast
import math
import re

_RATE=re.compile(r'\b(?:tien\s+)?luong gio(?:\s+thuc tra)?(?:\s+cua cong viec(?:\s+dang lam)?)?(?:\s+vao)?(?:\s+ngay lam viec binh thuong|\s+ngay binh thuong|\s+binh thuong)?\b')
_HOURS=re.compile(r'\bso gio(?:\s+lam viec)?(?:\s+vao)?(?:\s+ban dem|\s+lam them)?\b')
_PERCENT=re.compile(r'(?:\bmuc\s+)?(?:\bit nhat\s+)?(\d+(?:[.,]\d+)?)\s*%')

class UnitMismatch(ValueError):pass

def _dimension(node):
    if isinstance(node,ast.Expression):return _dimension(node.body)
    if isinstance(node,ast.Name) and node.id in {'A','H'}:
        return (1,-1) if node.id=='A' else (0,1)
    if isinstance(node,ast.Constant) and type(node.value) in (int,float) and math.isfinite(node.value):return (0,0)
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return _dimension(node.operand)
    if not isinstance(node,ast.BinOp):raise ValueError('unsupported formula node')
    left,right=_dimension(node.left),_dimension(node.right)
    if isinstance(node.op,(ast.Add,ast.Sub)):
        if left!=right:raise UnitMismatch('unlike units added')
        return left
    if isinstance(node.op,ast.Mult):return tuple(a+b for a,b in zip(left,right))
    if isinstance(node.op,ast.Div):
        if isinstance(node.right,ast.Constant) and node.right.value==0:raise ValueError('zero divisor')
        return tuple(a-b for a,b in zip(left,right))
    raise ValueError('unsupported formula operator')

def hourly_formula_status(claim,source):
    """Inputs are already accent-folded. Unknown syntax is never a proof.

    A and H exist only when the cited source states hourly wage AND hour count.
    Literal source quotations retain their original layout for separate review.
    """
    if claim in source:return 'NOT_APPLICABLE'
    if not ('luong gio' in source and 'so gio' in source and '=' in source):return 'NOT_APPLICABLE'
    if '=' not in claim or 'cong thuc' not in claim:return 'NOT_APPLICABLE'
    lhs,rhs=claim.rsplit('=',1)
    if not ('luong' in lhs and 'so gio' in rhs):return 'NOT_APPLICABLE'
    rhs=re.sub(r'\[[^\]]*\]','',rhs).strip().rstrip('.; ')
    rhs=_PERCENT.sub(lambda m:'('+m.group(1).replace(',','.')+'/100)',rhs)
    # Alternative percentage factors are all dimensionless; this does not
    # choose a rate or establish that any listed rate is legally applicable.
    rhs=re.sub(r'\(\d+(?:\.\d+)?/100\)(?:\s+hoac\s+\(\d+(?:\.\d+)?/100\))+','1',rhs)
    rhs=_HOURS.sub('H',rhs)
    rhs=_RATE.sub('A',rhs)
    for word,operator in [('nhan voi','*'),('nhan','*'),('cong voi','+'),('cong','+'),('chia cho','/'),('chia','/')]:
        rhs=re.sub(r'\b'+word+r'\b',operator,rhs)
    rhs=re.sub(r'\bx\b','*',rhs).replace('×','*').replace('·','*')
    if len(rhs)>512 or not re.fullmatch(r'[AH\d\s.+*/()\-]+',rhs):return 'UNKNOWN'
    depth=0
    for char in rhs:
        if char=='(':depth+=1
        elif char==')':depth-=1
        if depth<0 or depth>16:return 'UNKNOWN'
    if depth:return 'UNKNOWN'
    try:
        tree=ast.parse(rhs.strip(),mode='eval')
        if sum(1 for _ in ast.walk(tree))>64:return 'UNKNOWN'
        dimension=_dimension(tree)
        # A total multiplied by hour count must be money, not money/hour.
        return 'VALID' if dimension==(1,0) else 'UNIT_MISMATCH'
    except UnitMismatch:return 'UNIT_MISMATCH'
    except (ValueError,SyntaxError,TypeError,OverflowError,RecursionError):return 'UNKNOWN'
