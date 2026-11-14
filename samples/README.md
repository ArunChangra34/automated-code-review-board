# Sample Pull Request Diffs

This directory contains representative test diffs used for unit testing, integration regression suites, and live demonstrations of the Automated Code Review Board.

> **Security Note:** All API keys, tokens, and hashes present in these test diffs are synthetic dummy examples.

## Sample Inventory

| File | Primary Characteristics | Expected Decision | Key Findings |
|---|---|---|---|
| `01_clean_change.diff` | Small, clean Python utility with docstrings, type hints, and complete test suite | **APPROVE** | No findings above LOW/INFO |
| `02_sql_injection_and_secret.diff` | Database repository introducing raw SQL string interpolation and a hard-coded API key, without test coverage | **REQUEST_CHANGES** | 2 CRITICAL findings (SQL injection, hard-coded secret), corroboration across security/style/coverage, verified automated patch |
| `03_untested_feature.diff` | Substantial new domain business logic (discount engine) without any corresponding test changes | **REQUEST_CHANGES** | HIGH severity untested business logic findings |
| `04_style_mess.diff` | Non-idiomatic Python with long lines, uppercase function names, bare exceptions, wildcard imports, and debug logs | **REQUEST_CHANGES** | Multiple MEDIUM/LOW style and maintainability findings exceeding risk threshold |
| `05_mixed_realistic.diff` | Polyglot multi-file diff touching Python, JavaScript, YAML configuration, and dependency manifest | **REQUEST_CHANGES** | Findings spanning Security (`shell=True`, weak MD5, raw innerHTML), Config secret, and unpinned dependency |
