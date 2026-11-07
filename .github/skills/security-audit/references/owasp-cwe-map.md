# OWASP and CWE quick map

Compact lookup for `Category: security/<class> · CWE-<id> · OWASP <code>`. Labels use OWASP Top 10 (2021) and the
OWASP API Security Top 10 (2023). If the repository or its security policy uses a newer edition, use that
edition's code and keep the CWE id. Pick the most specific CWE that fits; when two fit, name the root cause.

## Injection and input handling (OWASP A03:2021 Injection)

| Class | CWE |
|---|---|
| SQL injection | CWE-89 |
| OS command injection | CWE-78 |
| Code injection (`eval`-like) | CWE-94 |
| NoSQL / query-logic injection | CWE-943 |
| LDAP injection | CWE-90 |
| Server-side template injection | CWE-1336 |
| Cross-site scripting | CWE-79 |
| Improper input validation (general) | CWE-20 |

## Access control (OWASP A01:2021 Broken Access Control; API1/API3/API5:2023)

| Class | CWE |
|---|---|
| Missing authorization | CWE-862 |
| Incorrect authorization | CWE-863 |
| IDOR / user-controlled key bypass (API1 BOLA) | CWE-639 |
| Path traversal | CWE-22 |
| Open redirect | CWE-601 |
| CSRF | CWE-352 |
| Exposure of sensitive data to unauthorized actor (API3) | CWE-200 |
| Mass assignment (API3) | CWE-915 |
| Permissive cross-origin policy | CWE-942 |

## Authentication and sessions (OWASP A07:2021; API2:2023)

| Class | CWE |
|---|---|
| Improper authentication | CWE-287 |
| Missing authentication for critical function | CWE-306 |
| No limit on authentication attempts | CWE-307 |
| Session fixation | CWE-384 |
| Insufficient session expiration | CWE-613 |
| Weak password requirements | CWE-521 |
| Signature not verified (for example unsigned tokens accepted) | CWE-347 |

## Cryptography and secrets (OWASP A02:2021 Cryptographic Failures)

| Class | CWE |
|---|---|
| Hard-coded credentials | CWE-798 |
| Hard-coded cryptographic key | CWE-321 |
| Cleartext storage of sensitive data | CWE-312 |
| Cleartext transmission | CWE-319 |
| Missing encryption of sensitive data | CWE-311 |
| Broken or risky algorithm | CWE-327 |
| Weak password hashing (too fast) | CWE-916 |
| Predictable random values for security | CWE-338 |
| Certificate validation disabled | CWE-295 |
| Timing-unsafe comparison | CWE-208 |

## Design and configuration (OWASP A04:2021 Insecure Design, A05:2021 Security Misconfiguration; API8:2023)

| Class | CWE |
|---|---|
| XML external entities | CWE-611 |
| Clickjacking (no frame restriction) | CWE-1021 |
| Incorrect default permissions | CWE-276 |
| Incorrect permission on critical resource (public bucket, world-writable file) | CWE-732 |
| Exposure of resource to wrong sphere (service exposed publicly) | CWE-668 |
| Improper privilege management / escalation path | CWE-269 |
| Running with unnecessary privileges | CWE-250 |
| Active debug code | CWE-489 |
| Error message reveals internals | CWE-209 |
| Cookie without Secure flag | CWE-614 |
| Cookie without HttpOnly flag | CWE-1004 |
| Unrestricted file upload | CWE-434 |
| Sensitive data in GET query string | CWE-598 |

## Integrity and supply chain (OWASP A06:2021, A08:2021)

| Class | CWE |
|---|---|
| Insecure deserialization of untrusted data | CWE-502 |
| Dependency with known vulnerability | CWE-1395 |
| Unmaintained third-party component | CWE-1104 |
| Prototype pollution | CWE-1321 |

## Logging and monitoring (OWASP A09:2021)

| Class | CWE |
|---|---|
| Sensitive data written to logs | CWE-532 |
| Insufficient logging of security events | CWE-778 |

## SSRF (OWASP A10:2021; API7:2023)

| Class | CWE |
|---|---|
| Server-side request forgery | CWE-918 |

## Resource abuse (API4:2023 Unrestricted Resource Consumption)

| Class | CWE |
|---|---|
| Uncontrolled resource consumption | CWE-400 |
| Allocation without limits | CWE-770 |
| Regular-expression denial of service | CWE-1333 |

## Memory safety (languages without it)

| Class | CWE |
|---|---|
| Out-of-bounds write | CWE-787 |
| Out-of-bounds read | CWE-125 |
| Use after free | CWE-416 |
| Integer overflow | CWE-190 |
| Time-of-check to time-of-use race | CWE-367 |
