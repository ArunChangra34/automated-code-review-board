# Secure Remediation Recipes and Patch Patterns

## RECIPE-SEC-SQLI-001: Parameterized Database Queries
To remediate SQL injection vulnerabilities, replace f-strings and string concatenations with parameterized SQL queries:
- Vulnerable:
  ```python
  cursor.execute(f"SELECT id, username FROM users WHERE username = '{username}'")
  ```
- Fixed:
  ```python
  cursor.execute(
      "SELECT id, username FROM users WHERE username = %s",
      (username,),
  )
  ```
For SQLite or standard DB-API drivers, use `?` or `%s` placeholders.

## RECIPE-SEC-SECRET-001: Environment Variable Credential Retrieval
To eliminate hard-coded secrets, load credentials from the process environment:
- Vulnerable:
  ```python
  API_KEY = "AKIAIOSFODNN7EXAMPLE12"
  ```
- Fixed:
  ```python
  import os
  API_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
  ```
Follow-up: Ensure any leaked credentials committed to version control are immediately revoked and rotated.

## RECIPE-SEC-CMDI-001: Argument List Subprocess Invocation
To eliminate shell command injection vulnerabilities, pass command arguments as a list with `shell=False`:
- Vulnerable:
  ```python
  subprocess.check_output(f"sh /scripts/{script_name}", shell=True)
  ```
- Fixed:
  ```python
  subprocess.check_output(["sh", f"/scripts/{script_name}"], shell=False)
  ```

## RECIPE-SEC-CRYPTO-001: Secure Cryptographic Hashing
Replace broken cryptographic hash algorithms (MD5, SHA1) with SHA-256:
- Vulnerable:
  ```python
  token_hash = hashlib.md5(user_token.encode()).hexdigest()
  ```
- Fixed:
  ```python
  token_hash = hashlib.sha256(user_token.encode()).hexdigest()
  ```

## RECIPE-SEC-DESER-001: Safe YAML Deserialization
Replace unsafe YAML loading with `yaml.safe_load`:
- Vulnerable:
  ```python
  data = yaml.load(payload, Loader=yaml.Loader)
  ```
- Fixed:
  ```python
  data = yaml.safe_load(payload)
  ```

## RECIPE-SEC-TLS-001: Enforce TLS Certificate Verification
Remove `verify=False` from HTTP request invocations:
- Vulnerable:
  ```python
  response = requests.get(url, verify=False)
  ```
- Fixed:
  ```python
  response = requests.get(url, verify=True)
  ```

## RECIPE-STY-EXCEPT-001: Specific Exception Handling
Replace bare `except:` clauses with explicit exception types:
- Vulnerable:
  ```python
  except:
      logger.error("Operation failed")
  ```
- Fixed:
  ```python
  except Exception as err:
      logger.error("Operation failed: %s", err)
  ```

## RECIPE-TST-SKELETON-001: Skeleton Test Template
Add a skeleton test file for untested public functions:
- Template:
  ```python
  import pytest
  from src.module import target_function

  def test_target_function_nominal():
      assert target_function() is not None
  ```
