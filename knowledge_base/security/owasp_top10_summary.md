# OWASP Top 10 Security Architecture Summary

## OWASP-A01: Broken Access Control
Access control enforces policy such that users cannot act outside of their intended permissions. Failures typically lead to unauthorized information disclosure, modification, or destruction of all data or performing a business function outside the user's limits. Ensure user identity and authorization checks guard every sensitive resource.

## OWASP-A02: Cryptographic Failures
Protect data in transit and at rest using modern, industry-standard cryptographic primitives. Avoid legacy algorithms like MD5, SHA-1, DES, or RC4 for integrity checks or password storage. Always enforce TLS 1.3 with validated certificates.

## OWASP-A03: Injection
Injection flaws, such as SQL, NoSQL, OS command, and LDAP injection, occur when untrusted data is sent to an interpreter as part of a command or query. Attackers can execute unintended commands or access unauthorized data without credentials. Always use parameterized queries or command argument lists.

## OWASP-A04: Insecure Design
Insecure design represents a broad category representing weaknesses expressed as missing or ineffective control design. Threat modeling, secure design patterns, and reference architectures are essential mitigations.

## OWASP-A05: Security Misconfiguration
Ensure secure defaults, disable unnecessary features and ports, remove default accounts and passwords, and keep software updated. Never enable debug flags or permissive CORS wildcards in production deployments.

## OWASP-A06: Vulnerable and Outdated Components
Components such as libraries and dependencies execute with the same privileges as the application itself. If a vulnerable component is exploited, it can facilitate serious data loss or server takeover. Pin dependencies and verify package authenticity.

## OWASP-A07: Identification and Authentication Failures
Authentication confirms user identity. Weak session management, lack of multi-factor authentication, or exposed credentials compromise account integrity.

## OWASP-A08: Software and Data Integrity Failures
Code and infrastructure that does not protect against integrity violations is vulnerable. Examples include insecure deserialization (e.g. Python pickle or unsafe YAML loaders) and untrusted CI/CD pipelines.

## OWASP-A09: Security Logging and Monitoring Failures
Without logging and monitoring, breaches cannot be detected. Ensure audit trails capture security events while strictly redacting all sensitive credentials and PII.

## OWASP-A10: Server-Side Request Forgery (SSRF)
SSRF flaws occur whenever a web application fetches a remote resource without validating the user-supplied URL. Validate and sanitize destination endpoints.
