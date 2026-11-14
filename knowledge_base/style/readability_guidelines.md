# Code Readability and Maintainability Principles

## STY-READ-001: Deep Nesting Minimization
Avoid code nested deeper than 3 or 4 levels of control flow indentation. Deep nesting severely increases cognitive load. Use early return statements (guard clauses) to exit preconditions early.

## STY-READ-002: Single Level of Abstraction
Functions should operate at a single consistent level of abstraction. High-level orchestrating functions should not interleave low-level bitwise operations or raw socket manipulation directly with business domain logic.

## STY-READ-003: DRY Principle and Duplicate Code Blocks
Duplicated logic across changes increases maintenance overhead and leads to inconsistent bug fixes. Extract repeated logic into reusable utility functions or shared components.

## STY-READ-004: Descriptive Parameter Signatures
Functions with more than four or five parameters should be refactored to accept a configuration dataclass, pydantic model, or options object to enhance call-site readability.
