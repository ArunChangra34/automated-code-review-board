# Python Style and Quality Rules

## STY-LEN-001: Maximum Line Length
Code lines should not exceed 100 characters in length. Extremely long lines impair readability on standard split screens and terminal diff tools. Break long expressions using parentheses or auxiliary variables.

## STY-NAME-001: Function and Variable Naming
Function and variable names must follow `snake_case` conventions. Names must be lowercase with words separated by underscores (e.g., `calculate_discount`, `user_record`). Avoid uppercase abbreviations or mixed camelCase.

## STY-NAME-002: Class Naming
Classes must adhere to `PascalCase` (UpperCamelCase) conventions (e.g., `UserAccountRepository`, `PaymentGateway`). Do not use lowercase or snake_case for class definitions.

## STY-NAME-003: Constant Naming
Module-level constants intended to remain immutable should use `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT_SECONDS`, `MAX_RETRIES`).

## STY-DOC-001: Public Interface Documentation
Every newly added public module, class, method, and function must include a clear docstring explaining its purpose, parameters, return value, and exceptions raised.

## STY-COMPLEX-001: Cyclomatic Complexity
Functions should maintain a cyclomatic complexity score of 10 or less. High cyclomatic complexity indicates excessive branching, deep nesting, and elevated defect probability. Refactor complex branches into smaller helper functions.

## STY-LEN-002: Maximum Function Length
Functions should not exceed 60 executable lines of code. Excessively long functions indicate violations of the Single Responsibility Principle and make unit testing difficult.

## STY-DEBUG-001: Leftover Debug Print Statements
Production code should not contain raw `print()` statements. Use structured logging (`logging.getLogger()`) with appropriate severity levels instead of ad-hoc standard output statements.

## STY-DEAD-001: Commented-Out Dead Code
Blocks of commented-out code clutter source files and generate confusion regarding intent. Version control systems preserve historical code; dead code must be deleted before merging.

## STY-EXCEPT-001: Bare Except Clauses
Never use a bare `except:` clause without specifying the exception class. Bare except catches system-exiting exceptions including `KeyboardInterrupt` and `SystemExit`. Use `except Exception:` or catch explicit exceptions.

## STY-IMPORT-001: Wildcard Imports
Avoid wildcard imports (`from module import *`). Wildcard imports pollute the namespace, obscure symbol origins, and defeat automated static analysis and linting.

## STY-MUTABLE-001: Mutable Default Arguments
Never use mutable default arguments (such as `[]` or `{}`) in function signatures. Default arguments are evaluated once at function definition time, resulting in shared state across invocations. Use `None` as default and initialize inside the function.

## STY-WS-001: Trailing Whitespace
Lines must not contain trailing spaces or tabs, and files should terminate with a single newline character.

## STY-TODO-001: Unlinked TODO Annotations
TODO and FIXME comments must include an associated issue tracker identifier (e.g., `TODO(PROJ-123): refactor`). Unassigned TODO comments accumulate technical debt indefinitely.

## STY-MAGIC-001: Magic Numbers in Logic
Avoid raw numeric literals in conditional or computational logic without explanation. Define named constants with semantic meaning.
