# Unit Test Patterns

Reference loaded on demand by `qa-unit-test` agent. Code templates per language. Read only the section needed.

## TypeScript / Jest

```typescript
import { functionName } from '../src/module';
import { mockDep } from '../src/dep';

jest.mock('../src/dep');
const mockDepInstance = mockDep as jest.Mocked<typeof mockDep>;

describe('functionName', () => {
  beforeEach(() => jest.clearAllMocks());

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

  it('handles unicode', () => {
    expect(sanitize('héllo wörld')).toBe('héllo wörld');
    expect(sanitize('<script>alert(1)</script>')).not.toContain('<script>');
  });

  it('logs error on DB failure', async () => {
    mockDepInstance.save.mockRejectedValue(new Error('connection lost'));
    await expect(createUser({} as any)).rejects.toThrow();
    expect(logger.error).toHaveBeenCalledWith(
      expect.stringContaining('connection lost'), expect.any(Error)
    );
  });

  it('uses cache, skips DB on second call', async () => {
    await getUser(1); await getUser(1);
    expect(mockDepInstance.findById).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['UTC', 0],
    ['IST', 5.5 * 60],
    ['Pacific', -8 * 60]
  ])('handles %s timezone offset %i min', (_, offsetMin) => {
    const mockDate = new Date(Date.UTC(2024, 0, 15, 12 - offsetMin / 60, 0, 0));
    jest.setSystemTime(mockDate);
    const result = formatDate(new Date());
    expect(result).toBeDefined();
  });

  it('avoids floating point precision errors', () => {
    expect(addAmounts(0.1, 0.2)).toBeCloseTo(0.3, 10);
  });
});
```

## Python / pytest

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
    def test_happy(self, mock_db):
        result = function_name({'id': 1})
        assert result == {'id': 1, 'name': 'Alice'}
        mock_db.query.assert_called_once_with(id=1)

    def test_none_raises(self):
        with pytest.raises(ValueError, match='required'):
            function_name(None)

    @pytest.mark.parametrize('payload', [None, '', [], 0, -1, 'x' * 10001])
    def test_boundary(self, payload, mock_db):
        try:
            function_name(payload)
        except (ValueError, TypeError):
            pass

    def test_unicode(self):
        assert sanitize('héllo') == 'héllo'

    def test_logs_on_error(self, mock_db, caplog):
        mock_db.save.side_effect = Exception('boom')
        with pytest.raises(Exception):
            create_user({})
        assert 'boom' in caplog.text

    def test_idempotent(self, mock_db):
        r1 = process_order({'id': 1})
        r2 = process_order({'id': 1})
        assert r1 == r2
        assert mock_db.save.call_count == 1
```

## Java / JUnit 5 + Mockito

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
    void handlesBlank(String input) {
        assertThrows(ValidationException.class, () -> service.functionName(input));
    }
}
```

## C# / NUnit + Moq

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

## Coverage checklist (apply to every function)

- Happy path
- Boundary values (null, empty, zero, negative, huge, off-by-one)
- Error cases (invalid type, missing field, dependency failure)
- Side effects (mock + verify args)
- Async edge cases (concurrent, rejection propagation)
- Type coercion (TS/JS only)
- Non-call verification (cache hit must not call DB)
- Unicode + special chars
- Logger called on error
- Idempotency
- Constructor injection (throws on missing dep)
- Time zone handling (3 offsets)
- Floating-point precision (money/percent math)
