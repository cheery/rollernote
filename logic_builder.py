from __future__ import annotations
from typing import Union, Optional, Any
from dataclasses import dataclass
import logic_ast as ast
import logic as core

@dataclass
class Builder:
    datadecls : dict[(str, int), (list[str], int)]
    typedecls : dict[(str, int), (bool, list[str], int)]
    rules : dict[(str, int), ast.RuleDeclaration]
    chrd : list[ast.CHRDeclaration]
    query : Optional[ast.Goal]
