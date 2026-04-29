---
name: code-analyzer
description: >
  Internal shared skill — scans a codebase and produces structured JSON metadata consumed by
  all test-generation skills. Always invoked first by test-orchestrator; rarely triggered standalone.

  Standalone use: when the user asks to understand project structure without generating tests.
  English: "map my project structure", "show me all endpoints", "what does this codebase contain",
  "analyze my code structure", "list all API routes".
  Hebrew (עברית): "מפה את מבנה הפרויקט", "הצג את כל ה-endpoints", "מה יש בקוד הזה",
  "נתח את מבנה הקוד", "רשום את כל ה-routes".
---

# code-analyzer

Produces a structured JSON map of a codebase. All other test skills consume this output.

## Phase 1 — Discovery

Recursively scan the given path. Respect these skip patterns:
```
node_modules/  __pycache__/  .git/  dist/  build/  .next/  target/  bin/  obj/
*.min.js  *.map  *.lock  *.sum  *.mod (go)
```

Detect primary language(s):
| Signal | Language |
|--------|----------|
| `package.json` present | TypeScript/JavaScript |
| `requirements.txt` or `pyproject.toml` | Python |
| `pom.xml` or `build.gradle` | Java/Kotlin |
| `*.csproj` or `*.sln` | C#/.NET |
| Multiple signals | Multi-language project |

## Phase 2 — Per-file analysis

For each non-skipped source file, compute:

**Hash**: SHA-256 of raw file bytes. Use Python:
```python
import hashlib
with open(path, "rb") as f:
    sha256 = hashlib.sha256(f.read()).hexdigest()
```

**Module type** (infer from content):
- `service` — business logic, no HTTP handlers
- `controller` — HTTP route handlers
- `model` — data structures, ORM entities
- `util` — helpers, pure functions
- `middleware` — request pipeline interceptors
- `frontend` — HTML, JSX/TSX components, Vue SFCs

**Pattern detection by language:**

### TypeScript / JavaScript
```
exports:      /^export\s+(async\s+)?function\s+(\w+)/
exports:      /^export\s+(default\s+)?class\s+(\w+)/
routes:       /router\.(get|post|put|patch|delete)\(['"]([^'"]+)['"]/
routes:       /@(Get|Post|Put|Patch|Delete)\(['"]([^'"]+)['"]\)/  (NestJS)
db_queries:   /\.query\(|\.find\(|\.findOne\(|\.save\(|\.execute\(/
auth:         /jwt|passport|bcrypt|hashPassword|verifyToken|@Guard/i
input_fields: /<input\s|req\.body\.|@Body\(\)|request\.form/
http_calls:   /fetch\(|axios\.|httpClient\.|HttpClient/
```

### Python
```
exports:      /^def\s+(\w+)/  (top-level or class methods)
exports:      /^class\s+(\w+)/
routes:       /@app\.route\(['"]([^'"]+)['"]/
routes:       /@router\.(get|post|put|patch|delete)\(['"]([^'"]+)['"]/
db_queries:   /\.query\(|\.filter\(|\.execute\(|session\.|db\./
auth:         /jwt|bcrypt|login_required|@requires_auth|verify_token/i
input_fields: /request\.form|request\.json|request\.data|@validator/
http_calls:   /requests\.(get|post)|httpx\.|aiohttp\./
```

### Java / Kotlin
```
exports:      /public\s+(static\s+)?\w+\s+(\w+)\s*\(/
exports:      /public\s+class\s+(\w+)/
routes:       /@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\(['"]([^'"]+)['"]\)/
db_queries:   /\.find\(|\.save\(|\.query\(|EntityManager|JdbcTemplate/
auth:         /@PreAuthorize|@Secured|JwtFilter|BCryptPasswordEncoder/i
input_fields: /@RequestBody|@RequestParam|@PathVariable/
http_calls:   /RestTemplate|WebClient|HttpClient/
```

### C# / .NET
```
exports:      /public\s+(async\s+)?\w+\s+(\w+)\s*\(/
exports:      /public\s+class\s+(\w+)/
routes:       /\[Http(Get|Post|Put|Delete|Patch)\("?([^"]*)"?\)\]/
routes:       /\[Route\("([^"]+)"\)\]/
db_queries:   /\.Find\(|\.Where\(|\.SaveChanges|_context\.|dbContext\./
auth:         /\[Authorize\]|JwtBearer|BCrypt|ClaimsPrincipal/i
input_fields: /\[FromBody\]|\[FromQuery\]|IFormFile/
http_calls:   /HttpClient|IHttpClientFactory/
```

## Phase 3 — Dependency mapping

For each module, list imports that reference other project files (not node_modules/stdlib):
```python
# TS/JS: parse import/require statements
# Python: parse import/from statements  
# Java: parse import statements (same package)
# C#: parse using statements (same namespace)
```

Only include intra-project dependencies — skip framework/library imports.

## Phase 4 — Output

Emit the following JSON. Write to stdout; do NOT write to disk (orchestrator handles that).

```json
{
  "language": "typescript",
  "additional_languages": [],
  "scanned_at": "ISO_TIMESTAMP",
  "project_root": "/absolute/path",
  "modules": [
    {
      "path": "src/auth/login.ts",
      "hash": "sha256hex",
      "type": "service",
      "exports": ["loginUser", "validateToken", "refreshToken"],
      "dependencies": ["src/db/users.ts", "src/utils/jwt.ts"],
      "has_db_queries": true,
      "has_http_calls": false,
      "has_auth": true,
      "input_fields": ["email", "password"]
    }
  ],
  "routes": [
    {
      "method": "POST",
      "path": "/auth/login",
      "handler": "loginUser",
      "file": "src/routes/auth.ts",
      "requires_auth": false
    }
  ],
  "frontend_files": [
    {
      "path": "src/components/LoginForm.tsx",
      "hash": "sha256hex",
      "has_forms": true,
      "has_navigation": false
    }
  ],
  "stats": {
    "total_files": 42,
    "by_type": { "service": 12, "controller": 8, "model": 6, "util": 10, "frontend": 6 },
    "has_auth": true,
    "has_db": true,
    "has_api": true,
    "has_frontend": true
  },
  "external_integrations": [
    { "vendor": "stripe", "sdk": "stripe", "file": "src/payments/charge.ts" }
  ],
  "uploads": [
    { "route": "POST /files/upload", "file": "src/routes/files.ts" }
  ],
  "graphql": {
    "schema_path": "src/schema.graphql",
    "resolvers": ["src/resolvers/user.ts"]
  },
  "state_machines": [
    { "name": "OrderStatus", "states": ["pending", "paid", "shipped", "cancelled"], "file": "src/models/order.ts" }
  ]
}
```

## Phase 3 — Extended detections

After per-file analysis, scan for these additional signals. Each defaults to `[]` / `null`
so existing skills tolerate their absence.

### External integrations

Detect third-party SDK usage. Output `external_integrations: [{vendor, sdk, file}]`.

```
stripe:         /stripe\.|Stripe\(/i
twilio:         /twilio\.|TwilioClient/i
sendgrid:       /sendgrid\.|SendGrid/i
aws:            /aws-sdk|@aws-sdk|boto3|AmazonS3/i
slack:          /WebClient|@slack\/web-api|slack_sdk/i
telegram:       /python-telegram-bot|telegraf|telebot/i
```

### File upload detection

Output `uploads: [{route, file}]` when upload middleware found:
```
multer:         /multer\(\)|upload\.(single|array|fields)\(/
formdata_js:    /FormData\(\)|req\.files/
iformfile:      /IFormFile/
flask_upload:   /request\.files/
```

### GraphQL detection

Output `graphql: { schema_path, resolvers: [] }` or `null`:
```
schema files:   /*.graphql$|/*.gql$/
resolvers_js:   /resolver|Resolver/i in *.ts/*.js
apollo:         /ApolloServer|@Resolver\(/
strawberry:     /strawberry\.|@strawberry/
```

### State machine detection

Output `state_machines: [{name, states: [], file}]`:
Detect enum/union types used inside switch statements.
```python
# TypeScript: enum Foo { A, B, C } + switch (x) { case Foo.A:
# Python: class Status(Enum) + if status ==
# Java: enum Status + switch(status)
# Pattern: find enum definition, check if enum values appear in switch/if-else chains
```

---

## What humans miss

The following patterns are commonly overlooked — always detect and flag them:

- **Unauthenticated routes**: routes where `requires_auth: false` but handler accesses DB
- **Direct object construction from user input**: `new Entity(req.body)` pattern (mass assignment risk)
- **Logging of sensitive fields**: `console.log(password)`, `logger.info(token)`
- **Missing error boundaries**: async functions with no try/catch
- **Hardcoded secrets**: `/api.key\s*=\s*['"][A-Za-z0-9]{20,}/` patterns

Flag these in a `warnings` array at the top level of the output:
```json
"warnings": [
  {
    "type": "unauthenticated_db_route",
    "file": "src/routes/users.ts",
    "line_hint": "GET /users handler calls findAll() without auth check",
    "severity": "high"
  }
]
```

## Notes

- If a file cannot be read (permissions, binary), skip it and add to `"skipped_files": []`
- If the project has fewer than 3 source files, warn: "Very small project — test generation may be incomplete"
- Do NOT run or execute any code from the scanned project
