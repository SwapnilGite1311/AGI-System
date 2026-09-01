"""
Safe arithmetic / math expression evaluation.

WHY THIS IS NOT A GENERAL PYTHON SANDBOX
----------------------------------------
The previous version of this module claimed to be one. It executed arbitrary
Python in `python -I -S` behind a denylist of AST node names, and it was
escapable in a single line:

    __builtins__.__dict__['__imp' + 'ort__']('os')

That reached `os`, `subprocess`, the environment and the filesystem - the
entire surface the module existed to deny. The denylist could not see
`__dict__`, and string concatenation defeated static name matching. Patching
the denylist is not a fix: a denylist over a Turing-complete language that
already has the interpreter loaded is the wrong shape of defence, and this
host has no container/VM/seccomp available to put underneath it.

So this module no longer executes Python. It *interprets* a small expression
grammar over an AST allowlist. There is no `exec`, no `eval`, no subprocess,
no import, no attribute access, no subscripting, and no name resolution
outside an explicit constant/function table - so there is no object graph to
walk and nothing to escape into. Anything the grammar does not name simply
cannot be expressed.

WHAT IT CAN DO
    arithmetic, percentages, powers, comparisons, and a fixed set of
    math/statistics functions:  2**10, 17/100*4500, sqrt(144),
    round(mean([1,2,3]), 2), max(3, 7)

WHAT IT DELIBERATELY CANNOT DO
    imports, file/network/process access, attribute access, indexing,
    assignment, loops, lambdas, comprehensions, or defining anything.
    General-purpose scripting is not available and should not be re-added
    here without real OS-level isolation underneath it.
"""

import ast
import math
import statistics
from typing import Any, Dict, List, Set

# Bare names that resolve to constants. Nothing else resolves at all.
ALLOWED_NAMES: Dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "True": True,
    "False": False,
    "None": None,
}

# Callables reachable by name. Deliberately all pure, total-ish, and
# side-effect free - no open/input/eval/getattr/type, no object introspection.
ALLOWED_FUNCTIONS: Dict[str, Any] = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "len": len, "pow": pow, "int": int, "float": float, "bool": bool,
    "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "log": math.log, "log2": math.log2, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "degrees": math.degrees, "radians": math.radians,
    "factorial": math.factorial, "gcd": math.gcd, "trunc": math.trunc,
    "mean": statistics.mean, "median": statistics.median,
    "mode": statistics.mode, "stdev": statistics.stdev,
    "variance": statistics.variance,
}

# Resource ceilings. An expression evaluator cannot loop, but it can still
# ask for absurd amounts of work/memory in one node (9**9**9, 10**100000,
# factorial(10**6)) - these bound that without needing a subprocess.
MAX_EXPRESSION_CHARS = 2000
MAX_AST_NODES = 500
MAX_EXPONENT = 1000
MAX_INT_DIGITS = 4300  # matches CPython's own int<->str conversion guard
MAX_SEQUENCE_LEN = 10000

_ALLOWED_NODES: Set[type] = {
    ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Compare, ast.Call, ast.Name, ast.Load, ast.List, ast.Tuple, ast.IfExp,
    # operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
}


class ExpressionError(Exception):
    """Raised when an expression is outside the permitted grammar."""


def _check_number(value: Any) -> Any:
    """Bound intermediate results so one node can't exhaust memory."""
    if isinstance(value, int) and not isinstance(value, bool):
        if value != 0 and len(str(abs(value))) > MAX_INT_DIGITS:
            raise ExpressionError("Result is too large to compute safely.")
    elif isinstance(value, (str, list, tuple)) and len(value) > MAX_SEQUENCE_LEN:
        raise ExpressionError("Result sequence is too large to compute safely.")
    return value


class _Evaluator(ast.NodeVisitor):
    """Interprets the permitted grammar. Never executes Python."""

    def visit(self, node):
        if type(node) not in _ALLOWED_NODES:
            raise ExpressionError(
                f"'{type(node).__name__}' is not allowed - this evaluator accepts "
                "arithmetic and math expressions only."
            )
        return super().visit(node)

    def generic_visit(self, node):
        raise ExpressionError(f"'{type(node).__name__}' is not allowed here.")

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float, str, bool, complex)) or node.value is None:
            return _check_number(node.value)
        raise ExpressionError("Only numeric, string and boolean literals are allowed.")

    def visit_Name(self, node):
        if node.id in ALLOWED_NAMES:
            return ALLOWED_NAMES[node.id]
        if node.id in ALLOWED_FUNCTIONS:
            return ALLOWED_FUNCTIONS[node.id]
        raise ExpressionError(
            f"Unknown name '{node.id}'. Available: "
            + ", ".join(sorted(list(ALLOWED_FUNCTIONS) + list(ALLOWED_NAMES))[:12])
            + ", ..."
        )

    def visit_List(self, node):
        return _check_number([self.visit(item) for item in node.elts])

    def visit_Tuple(self, node):
        return _check_number(tuple(self.visit(item) for item in node.elts))

    def visit_IfExp(self, node):
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return _check_number(-operand)
        if isinstance(node.op, ast.UAdd):
            return _check_number(+operand)
        if isinstance(node.op, ast.Not):
            return not operand
        raise ExpressionError("Unsupported unary operator.")

    def visit_BoolOp(self, node):
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            result = True
            for v in values:
                result = result and v
            return result
        result = False
        for v in values:
            result = result or v
        return result

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            else:
                raise ExpressionError("Unsupported comparison operator.")
            if not ok:
                return False
            left = right
        return True

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Pow):
            # Bound before computing: 9**9**9 would otherwise hang/OOM.
            if isinstance(right, (int, float)) and abs(right) > MAX_EXPONENT:
                raise ExpressionError(f"Exponent above {MAX_EXPONENT} is not allowed.")
            return _check_number(left ** right)
        if isinstance(node.op, ast.Mult):
            # Bound before computing: 'a' * 10**9 would otherwise allocate ~1GB.
            if isinstance(left, (str, list, tuple)) and isinstance(right, int):
                if len(left) * abs(right) > MAX_SEQUENCE_LEN:
                    raise ExpressionError("Result sequence is too large to compute safely.")
            if isinstance(right, (str, list, tuple)) and isinstance(left, int):
                if len(right) * abs(left) > MAX_SEQUENCE_LEN:
                    raise ExpressionError("Result sequence is too large to compute safely.")
            return _check_number(left * right)

        try:
            if isinstance(node.op, ast.Add):
                return _check_number(left + right)
            if isinstance(node.op, ast.Sub):
                return _check_number(left - right)
            if isinstance(node.op, ast.Div):
                return _check_number(left / right)
            if isinstance(node.op, ast.FloorDiv):
                return _check_number(left // right)
            if isinstance(node.op, ast.Mod):
                return _check_number(left % right)
        except ZeroDivisionError:
            raise ExpressionError("Division by zero.")
        raise ExpressionError("Unsupported operator.")

    def visit_Call(self, node):
        # Only bare `name(...)` calls - node.func must be a Name, so
        # `os.system(...)` or `x.__class__(...)` cannot parse as a call here.
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("Only direct calls to allowed functions are permitted.")
        if node.func.id not in ALLOWED_FUNCTIONS:
            raise ExpressionError(f"Function '{node.func.id}' is not available.")
        if node.keywords:
            raise ExpressionError("Keyword arguments are not supported.")

        func = ALLOWED_FUNCTIONS[node.func.id]
        args = [self.visit(a) for a in node.args]

        if func is math.factorial and args and isinstance(args[0], int) and args[0] > 1000:
            raise ExpressionError("factorial argument above 1000 is not allowed.")

        try:
            return _check_number(func(*args))
        except ExpressionError:
            raise
        except ZeroDivisionError:
            raise ExpressionError("Division by zero.")
        except Exception as exc:
            raise ExpressionError(f"{node.func.id}() failed: {exc}")


def evaluate_expression(expression: str) -> Dict[str, Any]:
    """Evaluate one arithmetic/math expression.

    Returns {"success", "result"/"error", "expression"}. Never raises, never
    executes Python, never touches the OS.
    """
    expression = (expression or "").strip()
    if not expression:
        return {"success": False, "error": "No expression provided."}
    if len(expression) > MAX_EXPRESSION_CHARS:
        return {"success": False, "error": f"Expression exceeds {MAX_EXPRESSION_CHARS} characters."}

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return {
            "success": False,
            "error": f"Could not parse that as a single expression: {exc.msg}",
            "expression": expression,
        }

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_AST_NODES:
        return {"success": False, "error": "Expression is too complex.", "expression": expression}

    try:
        result = _Evaluator().visit(tree)
    except ExpressionError as exc:
        return {"success": False, "error": str(exc), "expression": expression}
    except RecursionError:
        return {"success": False, "error": "Expression nests too deeply.", "expression": expression}
    except Exception as exc:  # pragma: no cover - defensive
        return {"success": False, "error": f"Evaluation failed: {exc}", "expression": expression}

    return {
        "success": True,
        "result": result,
        "output": str(result),
        "expression": expression,
    }


def describe_capabilities() -> str:
    """Human-readable summary, used in the tool description."""
    return (
        "Arithmetic and math expressions only (e.g. '17/100*4500', 'sqrt(144)', "
        "'round(mean([1,2,3]), 2)'). Functions: "
        + ", ".join(sorted(ALLOWED_FUNCTIONS)) + "."
    )
