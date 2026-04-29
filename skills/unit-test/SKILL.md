---
name: unit-test
description: >
  Generate comprehensive unit tests for code modules — functions, classes, services.
  Normally invoked by test-orchestrator as part of a full test run.
  Also usable standalone when the user asks to test a specific file or module directly.

  English triggers (standalone): "write unit tests for [file]", "test this function",
  "add unit tests to [module]", "improve test coverage for [path]", "find edge cases in [file]".

  Hebrew triggers (עברית): "כתוב בדיקות יחידה ל-[קובץ]", "בדוק את הפונקציה הזאת",
  "הוסף בדיקות יחידה ל-[מודול]", "שפר כיסוי בדיקות", "מצא מקרי קצה ב-[קובץ]".

  Supports TypeScript/Jest/Vitest, Python/pytest, Java/JUnit 5, C#/NUnit.
---

# unit-test

Generates exhaustive unit tests for every exported function and class in each module.

> **User-facing messages**: use `get_message(key, locale, **kwargs)` from
> `skills/_shared/validate.py`. Message keys defined in `skills/_shared/messages/{he,en}.json`.
> Never hardcode user-facing strings — use message keys so Hebrew/English stays consistent.

## Inputs

Receives from `test-orchestrator`:
```json
{
  "modules": [/* module objects from code-analyzer */],
  "project_root": "string",
  "language": "string",
  "run_type": "full | incremental"
}
```

## Framework selection

Detect from project config — do NOT assume:

| Language | Check | Framework |
|----------|-------|-----------|
| TypeScript/JS | `package.json` has `"jest"` | Jest |
| TypeScript/JS | `package.json` has `"vitest"` | Vitest |
| TypeScript/JS | neither | Jest (default) |
| Python | always | pytest + unittest.mock |
| Java | `pom.xml` has `junit-jupiter` | JUnit 5 + Mockito |
| Kotlin | same | JUnit 5 + MockK |
| C# | `*.csproj` | NUnit + Moq |

## Output location

```
{project_root}/tests/unit/{mirrored_path}.test.{ext}

Examples:
  src/auth/login.ts        → tests/unit/auth/login.test.ts
  src/services/user.py     → tests/unit/services/test_user.py
  src/main/java/UserSvc.java → src/test/java/UserSvcTest.java  (Maven convention)
  Services/UserService.cs  → Tests/Unit/UserServiceTests.cs
```

Create directories as needed.

## What to generate for every function/method

### 1. Happy path
The normal, expected usage with valid inputs. Assert return value and/or side effects.

### 2. Boundary values — always include all that apply
- `null` / `None` / `nil` input
- Empty string `""`
- Empty array/list `[]`
- Zero `0` and negative numbers
- Maximum integer / very large string (>10,000 chars)
- Off-by-one: test `n-1`, `n`, `n+1` for any size-based logic

### 3. Error cases
- Invalid input types → expect TypeError / ValueError / ArgumentException
- Missing required fields → expect validation error
- Simulated network failure (mock throws) → verify error propagated or handled
- Simulated timeout → verify timeout error surface

### 4. Side effects — mock and verify
- DB calls: mock the DB layer, verify it was called with correct args
- HTTP calls: mock fetch/axios/requests, verify URL and method
- Logger: mock logger, verify error logging happens on failure
- Events/queues: mock emit, verify message structure

### 5. Async edge cases (only if function is async)
- Concurrent calls: call twice simultaneously, verify no race corruption
- Promise rejection propagation
- Cancellation / abort signal behavior (if applicable)

### 6. Type coercion bugs (TypeScript/JavaScript only)
- `"1"` vs `1` — if function accepts `id`, test both string and number
- `undefined` vs `null` — test both explicitly
- `false` vs `0` vs `""` — falsy value disambiguation
- `NaN` input where number expected

## Additional "what testers miss" — Phase 8 additions

**Time-zone bugs** — every function touching dates/times must be tested with 3 timezones:
```typescript
it.each([
  ['UTC', 0],
  ['IST', 5.5 * 60],    // +05:30
  ['Pacific', -8 * 60]  // -08:00
])('handles %s timezone offset %i min', (tz, offsetMin) => {
  const mockDate = new Date(Date.UTC(2024, 0, 15, 12 - offsetMin / 60, 0, 0));
  jest.setSystemTime(mockDate);
  const result = formatDate(new Date());
  expect(result).not.toContain('Invalid');
  expect(result).toBeDefined();
});
```

**Floating point precision** — for any function doing math with money or percentages:
```typescript
it('avoids floating point precision errors', () => {
  // The classic 0.1 + 0.2 trap
  expect(addAmounts(0.1, 0.2)).toBeCloseTo(0.3, 10);
  expect(addAmounts(1.005, 0)).toBeCloseTo(1.005, 2);
});
```

**Promise rejection propagation**:
```typescript
it('propagates rejection without swallowing error', async () => {
  mockDep.call.mockRejectedValue(new Error('network failure'));
  await expect(functionUnderTest()).rejects.toThrow('network failure');
  // Verify the error was NOT silently caught and ignored
});
```

## What humans miss — mandatory inclusions

These are systematically skipped by human testers. Include them:

**Non-call verification**: assert DB is NOT called when function uses cached data
```typescript
it('uses cache, skips DB on second call', async () => {
  await getUser(1); await getUser(1);
  expect(db.findById).toHaveBeenCalledTimes(1); // not 2
});
```

**Unicode and special characters**:
```typescript
it('handles unicode input', () => {
  expect(sanitize('héllo wörld')).toBe('héllo wörld');
  expect(sanitize('<script>alert(1)</script>')).not.toContain('<script>');
});
```

**Logger mock — verify error is logged**:
```typescript
it('logs error on DB failure', async () => {
  db.save.mockRejectedValue(new Error('connection lost'));
  await expect(createUser(data)).rejects.toThrow();
  expect(logger.error).toHaveBeenCalledWith(
    expect.stringContaining('connection lost'), expect.any(Error)
  );
});
```

**Idempotency**:
```typescript
it('returns same result on repeated calls', async () => {
  const r1 = await processOrder(order);
  const r2 = await processOrder(order);
  expect(r1).toEqual(r2);
  expect(db.save).toHaveBeenCalledTimes(1); // not 2 — guard against double-save
});
```

**Constructor injection / dependency integrity**:
```typescript
it('throws if required dependency missing', () => {
  expect(() => new UserService(null)).toThrow(/dependency/i);
});
```

## Code templates

### TypeScript (Jest)
```typescript
import { functionName } from '../src/module';
import { mockDep } from '../src/dep';

jest.mock('../src/dep');
const mockDepInstance = mockDep as jest.Mocked<typeof mockDep>;

describe('functionName', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns expected value for valid input', async () => {
    mockDepInstance.query.mockResolvedValue({ id: 1, name: 'Alice' });
    const result = await functionName({ id: 1 });
    expect(result).toEqual({ id: 1, name: 'Alice' });
    expect(mockDepInstance.query).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  it('throws ValidationError for null input', async () => {
    await expect(functionName(null)).rejects.toThrow('ValidationError');
  });

  it('handles empty string gracefully', async () => {
    const result = await functionName({ name: '' });
    expect(result).toBeDefined();
  });
});
```

### Python (pytest)
```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.module import function_name

@pytest.fixture
def mock_db():
    with patch('src.module.db') as mock:
        mock.query.return_value = {'id': 1, 'name': 'Alice'}
        yield mock

class TestFunctionName:
    def test_returns_expected_for_valid_input(self, mock_db):
        result = function_name({'id': 1})
        assert result == {'id': 1, 'name': 'Alice'}
        mock_db.query.assert_called_once_with(id=1)

    def test_raises_for_none_input(self):
        with pytest.raises(ValueError, match='required'):
            function_name(None)

    def test_handles_empty_string(self, mock_db):
        mock_db.query.return_value = []
        result = function_name({'name': ''})
        assert result is not None

    @pytest.mark.parametrize('payload', [
        None, '', [], 0, -1, 'x' * 10001
    ])
    def test_boundary_inputs(self, payload, mock_db):
        # Should not crash — either return empty or raise ValueError
        try:
            result = function_name(payload)
        except (ValueError, TypeError):
            pass  # acceptable
```

### Java (JUnit 5 + Mockito)
```java
@ExtendWith(MockitoExtension.class)
class FunctionNameTest {
    @Mock private DependencyService dep;
    @InjectMocks private ServiceUnderTest service;

    @Test
    void returnsExpectedForValidInput() {
        when(dep.query(1L)).thenReturn(Optional.of(new Entity(1L, "Alice")));
        var result = service.functionName(1L);
        assertThat(result).isEqualTo(new Entity(1L, "Alice"));
        verify(dep).query(1L);
    }

    @Test
    void throwsForNullInput() {
        assertThrows(IllegalArgumentException.class, () -> service.functionName(null));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t"})
    void handlesBlankStrings(String input) {
        assertThrows(ValidationException.class, () -> service.functionName(input));
    }
}
```

### C# (NUnit + Moq)
```csharp
[TestFixture]
public class FunctionNameTests
{
    private Mock<IDependency> _dep;
    private ServiceUnderTest _service;

    [SetUp]
    public void SetUp()
    {
        _dep = new Mock<IDependency>();
        _service = new ServiceUnderTest(_dep.Object);
    }

    [Test]
    public async Task ReturnsExpectedForValidInput()
    {
        _dep.Setup(d => d.QueryAsync(1)).ReturnsAsync(new Entity { Id = 1, Name = "Alice" });
        var result = await _service.FunctionNameAsync(1);
        Assert.That(result.Name, Is.EqualTo("Alice"));
        _dep.Verify(d => d.QueryAsync(1), Times.Once);
    }

    [Test]
    public void ThrowsForNullInput()
    {
        Assert.ThrowsAsync<ArgumentNullException>(() => _service.FunctionNameAsync(null));
    }

    [TestCase(null), TestCase(""), TestCase("   ")]
    public void HandlesBlankInputs(string input)
    {
        Assert.ThrowsAsync<ValidationException>(() => _service.FunctionNameAsync(input));
    }
}
```

## Execute & fix loop

After writing test files, the orchestrator will run them via Bash and parse failures.
If the orchestrator reports failing tests back to this skill:

1. Read the failing test file
2. Read the source module
3. Fix root cause: wrong mock shape, wrong expected value, missing import, wrong function name
4. Fix **only** the failing test — leave passing tests untouched
5. Return updated file to orchestrator for re-run

Max 3 fix iterations. If still failing after 3, mark `status: "partial"` and document failures.

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/auth/login.ts",
    "path": "tests/unit/auth/login.test.ts",
    "tests_written": 12,
    "functions_covered": ["loginUser", "validateToken"],
    "status": "created | updated | partial",
    "execution_result": "passed | failed | not_run"
  }
]
```
