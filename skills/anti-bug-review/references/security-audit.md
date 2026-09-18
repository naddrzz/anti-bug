# Security Audit Reference

Read this for Pass B. The organizing principle: **follow the data, not the function names.** A grep for `eval(` finds candidate sinks; only a trace from an entry point tells you whether attacker-controlled data reaches one.

## The taint-tracing method

1. **Enumerate sources** from the Phase 0 entry points: HTTP params, query strings, headers, cookies, request bodies, uploaded files and their names, webhook payloads, message-queue payloads, CLI args, env vars in multi-tenant contexts, and anything read back out of the database that a user once wrote (stored injection is the one people forget).
2. **Enumerate sinks** for this stack: SQL/NoSQL query builders, shell/process execution, filesystem paths, template rendering, deserializers, HTTP clients, redirect targets, reflection/dynamic import, and log statements (for secret leakage).
3. **Trace each source forward** through function calls and assignments. At the sink, ask: is the value parameterized, escaped for *this* context, or validated against an allowlist? Context matters - HTML escaping does not protect a JS string context or an attribute context, and escaping does nothing for an injection into an identifier position in SQL.
4. Record the full path `source file:line -> transform -> sink file:line` as the finding's evidence. That path *is* the reproduction when a live request is impractical.

## CWE Top 25 (2025) as a worklist

Ordered as published by MITRE. Work top-down, skipping classes irrelevant to the stack (memory-safety entries rarely apply to managed languages).

| # | CWE | Weakness | Look for |
|---|---|---|---|
| 1 | 79 | Cross-site Scripting | Unescaped output in templates, `innerHTML`, `dangerouslySetInnerHTML`, `v-html`, markdown rendered without sanitization |
| 2 | 89 | SQL Injection | String concatenation or f-strings in queries, ORM `raw()`/`extra()`, dynamic `ORDER BY`/table names |
| 3 | 352 | CSRF | State-changing GET, missing/unverified CSRF token, `SameSite=None` without justification |
| 4 | 862 | Missing Authorization | Route with authentication but no ownership/role check - see the authorization section below |
| 5 | 787 | Out-of-bounds Write | C/C++/unsafe blocks: memcpy with attacker length, off-by-one in buffer indexing |
| 6 | 22 | Path Traversal | User input in file paths, `../` unfiltered, archive extraction (zip-slip), unchecked `join` of a user segment |
| 7 | 416 | Use After Free | C/C++/unsafe: freed pointer reused, double free |
| 8 | 125 | Out-of-bounds Read | C/C++: length from input, missing bounds check |
| 9 | 78 | OS Command Injection | `shell=True`, `exec`, backticks, `child_process.exec` with interpolated input |
| 10 | 94 | Code Injection | `eval`, `Function()`, `pickle.loads`, dynamic `require`/`import` of a user string |
| 11 | 120 | Buffer Copy w/o Size Check | `strcpy`, `sprintf`, `gets` |
| 12 | 434 | Unrestricted File Upload | Extension/MIME trusted from client, files written under the web root, no size cap |
| 13 | 476 | NULL Pointer Dereference | Return value used without a null check on the error path |
| 14 | 121 | Stack Buffer Overflow | Fixed-size stack buffers with variable-length input |
| 15 | 502 | Deserialization of Untrusted Data | `pickle`, `yaml.load` (non-safe), Java native deserialization, `unserialize` |
| 16 | 122 | Heap Buffer Overflow | Allocation size from arithmetic on input |
| 17 | 863 | Incorrect Authorization | Check exists but is wrong: role compared loosely, check after the action, client-supplied role |
| 18 | 20 | Improper Input Validation | Type/range/format unvalidated at the boundary; allowlist absent |
| 19 | 284 | Improper Access Control | Admin endpoints reachable, debug routes exposed, internal services unauthenticated |
| 20 | 200 | Sensitive Information Exposure | Stack traces to users, PII in logs, over-broad API serializers, secrets in error messages |
| 21 | 306 | Missing Authentication | Critical function with no auth at all (health/admin/internal endpoints) |
| 22 | 918 | SSRF | Server fetches a user-supplied URL; check for internal IPs, redirects, DNS rebinding, cloud metadata endpoints |
| 23 | 77 | Command Injection | Argument injection into a command built from parts |
| 24 | 639 | Authorization Bypass via User-Controlled Key | IDOR: `/orders/{id}` without an ownership check |
| 25 | 770 | Resource Allocation w/o Limits | No rate limit, unbounded upload/body size, unbounded allocation from a length field |

SQL Injection rose five places and Missing Authorization rose five places into the 2025 top five - injection and authorization remain the two classes worth the most attention in web codebases.

## OWASP Top 10 (2021) cross-check

Use as a second lens; it groups by risk rather than weakness.

- **A01 Broken Access Control** - the largest category. Enumerate every route and check each one.
- **A02 Cryptographic Failures** - MD5/SHA1 for passwords, ECB mode, hardcoded IVs, unsalted hashes, TLS verification disabled, secrets in source. Passwords need bcrypt/scrypt/argon2, not a general-purpose hash.
- **A03 Injection** - includes XSS, SQL, command, LDAP, template injection.
- **A04 Insecure Design** - missing rate limiting on auth, no account lockout, password reset tokens that do not expire or are not single-use.
- **A05 Security Misconfiguration** - debug mode, default credentials, verbose errors, permissive CORS, unnecessary features enabled.
- **A06 Vulnerable Components** - the dependency audit from Phase 1; check whether the vulnerable path is actually reachable before rating it Critical.
- **A07 Identification and Authentication Failures** - session fixation, tokens not invalidated on logout or password change, weak session expiry, JWT with `alg: none` or an unverified signature.
- **A08 Software and Data Integrity Failures** - unsigned updates, CI pulling unpinned dependencies, deserialization.
- **A09 Logging and Monitoring Failures** - security events not logged, or logs containing credentials/tokens/PII.
- **A10 SSRF** - see CWE-918 above.

## Authorization: the class tools cannot find

Scanners see syntax; authorization is semantics. Build a route inventory and answer four questions per route:

1. Is authentication required, and enforced server-side?
2. Is authorization checked *for the specific object*, not just the endpoint? (`can_view(user, invoice)`, not `is_logged_in(user)`)
3. Where does the identity come from? Anything user-supplied - a `user_id` body field, a role in a client-set header or an unverified JWT claim - is not identity.
4. Is the check before the effect? A permission check after the write has already happened is not a check.

Common shapes of the bug: the ID comes from the URL and is queried without scoping to the caller; the list endpoint scopes correctly but the detail endpoint does not; the UI hides the button and the API does not; an admin flag is read from the request; a bulk endpoint checks the first item only.

## Reviewing AI-generated code

Roughly 40% of LLM-generated programs in controlled security scenarios contained a CWE, concentrated in path traversal, OS command injection, null dereference, and weak credential protection (MD5 appearing where a password hash belongs). Recently AI-authored code deserves the security pass even when it looks idiomatic - it usually does. Also verify that every imported package actually exists on the registry: hallucinated package names are a live supply-chain attack surface ("slopsquatting"), where attackers register the names models invent.

## Severity calibration

Rate by exploitability and blast radius, not by scanner label.

- **Critical** - remote, unauthenticated, leads to data disclosure/modification, code execution, or auth bypass.
- **High** - requires authentication but crosses a tenant/user boundary, or exposes credentials.
- **Medium** - requires unusual preconditions, or leaks non-sensitive internals.
- **Low** - defense in depth, hardening, no demonstrated path.

State the preconditions explicitly for each. A finding that needs local root access is not the same as one reachable from the internet, and conflating them is how the Critical list stops being read.
