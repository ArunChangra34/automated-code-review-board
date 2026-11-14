# Injection Vulnerabilities and Unsafe API Patterns

## SEC-SQLI-001: SQL Injection via String Interpolation
Constructing SQL statements via f-strings, `%` formatting, or string concatenation allows attackers to inject malicious SQL fragments that manipulate database query execution. Always use parameterized queries (prepared statements) provided by DB-API, SQLAlchemy, or the database driver.

## SEC-CMDI-001: Command Injection via Subprocess Shell
Invoking `subprocess.Popen`, `subprocess.run`, `subprocess.call`, or `subprocess.check_output` with `shell=True` passes input strings directly to the system shell (`/bin/sh`), enabling arbitrary command chaining (e.g. `; rm -rf /`). Always pass an argument list with `shell=False`.

## SEC-DESER-001: Insecure Object Deserialization
Deserializing untrusted data with `pickle.loads()`, `marshal.loads()`, or `yaml.load()` without a safe loader permits remote code execution. In Python, `pickle` can instantiate arbitrary callable objects via `__reduce__`. Use `json.loads()` or `yaml.safe_load()`.

## SEC-EVAL-001: Dynamic Code Execution
Functions such as `eval()`, `exec()`, and `compile()` execute arbitrary code strings within the application context. Never invoke dynamic evaluation on user-controlled or external inputs. Use safe parsers such as `ast.literal_eval()`.

## SEC-XSS-001: Cross-Site Scripting via Direct DOM Injection
In web applications, assigning untrusted text directly to `element.innerHTML`, `document.write()`, or React's `dangerouslySetInnerHTML` allows attackers to execute arbitrary JavaScript in the victim's browser session. Use `textContent` or framework auto-sanitizing bindings.

## SEC-CRYPTO-001: Broken Cryptographic Hash Algorithms
Algorithms such as MD5 (`hashlib.md5`) and SHA-1 (`hashlib.sha1`) suffer from known collision attacks and must never be used for password hashing, digital signatures, or security tokens. Use SHA-256 for integrity checks and Argon2id or bcrypt for password hashing.

## SEC-CRYPTO-002: Insecure Pseudorandom Generators
Standard library `random` module produces predictable pseudorandom numbers based on the Mersenne Twister algorithm. For security tokens, password reset nonces, or session IDs, always use the cryptographically secure `secrets` module (`secrets.token_hex`, `secrets.token_urlsafe`).

## SEC-TLS-001: Disabled TLS Certificate Verification
Setting `verify=False` in HTTP client libraries (e.g., `requests.get(..., verify=False)`) disables SSL/TLS certificate validation, rendering connections vulnerable to Man-in-the-Middle (MitM) interception and credential theft.

## SEC-CORS-001: Overly Permissive CORS Headers
Setting `Access-Control-Allow-Origin: *` in combination with credentialed requests allows any third-party website to make authenticated cross-origin requests to internal APIs. Explicitly whitelist trusted origins.

## SEC-DEBUG-001: Production Debug Mode Enabled
Enabling `DEBUG = True` or exposing interactive debugger consoles in production leaks internal stack traces, system paths, configuration secrets, and may allow remote code execution through web debuggers.

## SEC-PATH-001: Path Traversal Vulnerabilities
Joining user-controlled filenames with directory paths using `os.path.join()` without verifying that the resolved path resides within the intended base directory permits path traversal (`../`) attacks. Validate paths using `Path.resolve()` and ensure they remain within the boundary directory.

## SEC-DEP-001: Unpinned Manifest Dependencies
Adding dependencies to package manifests without pinning versions (e.g., bare package names without `>=` or `==` version bounds) leaves the build pipeline vulnerable to supply chain attacks and unexpected breaking changes.
