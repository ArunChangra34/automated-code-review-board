# Unit and Integration Test Coverage Guidelines

## TST-UNTESTED-001: Untested Public Logic
Any new business logic, algorithmic calculation, public API endpoint, or data processing service must be accompanied by unit tests. Pull requests introducing functional code without corresponding test coverage represent a critical regression risk.

## TST-PARTIAL-001: Superficial or Incomplete Testing
Tests must execute meaningful assertions against system outputs, returned data structures, and state transitions. Test functions containing only mock invocations or empty `pass` statements provide false confidence and do not satisfy test verification criteria.

## TST-RATIO-001: Adequate Test-to-Code Ratio
For non-trivial feature branches, the volume of test code should correspond proportionally to the volume of production code added (minimum target ratio 0.60 to 1.0 test lines per source line).

## TST-ERR-001: Error Path and Edge Case Verification
Test suites must include negative test cases validating that improper inputs, boundary values, network failures, and bad state conditions raise appropriate exceptions (e.g., using `pytest.raises()`).
