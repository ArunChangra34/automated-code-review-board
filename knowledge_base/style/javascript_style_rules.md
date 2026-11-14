# JavaScript and TypeScript Style Guidelines

## STY-NAME-004: JavaScript Function and Variable Naming
Functions, methods, and variables in JavaScript and TypeScript must use `camelCase` (e.g., `calculateTotal`, `userId`). Class definitions and React components must use `PascalCase`.

## STY-DEBUG-002: Leftover Console Debugging
Calls to `console.log`, `console.debug`, and `console.warn` should not be checked into production code. Use a configurable logging framework or logger abstraction.

## STY-EQUALITY-001: Strict Equality Comparison
Always use strict equality operators (`===` and `!==`) instead of abstract equality (`==` and `!=`). Abstract equality allows subtle bugs resulting from automatic type coercion.

## STY-VAR-001: Prohibition of Var Keyword
Do not use the `var` keyword. Use `const` by default for variables that do not require reassignment, and `let` for variables whose values mutate within block scope.

## STY-ASYNC-001: Unhandled Promise Rejections
All asynchronous operations and promises must have appropriate error handling via `try/catch` with `async/await` or `.catch()` handlers.
