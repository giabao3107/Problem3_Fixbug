# Testing Suite for Realtime Alert System

This directory contains a comprehensive testing suite for the Realtime Alert System, including unit tests, integration tests, and performance benchmarks.

## 📁 Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Shared fixtures and test configuration
├── test_fiinquant_adapter.py   # FiinQuant adapter tests
├── test_strategy.py            # Trading strategy tests
├── test_cache_manager.py       # Cache management tests
├── test_alert_system.py        # Alert system tests
├── test_integration.py         # End-to-end integration tests
└── README.md                   # This file
```

## 🚀 Quick Start

### 1. Install Testing Dependencies

```bash
# Install all testing dependencies
pip install -r requirements-test.txt

# Or use make command
make install-dev
```

### 2. Run Tests

```bash
# Run all tests
python run_tests.py

# Or use make command
make test
```

## 🧪 Test Categories

### Unit Tests
Test individual components in isolation:

```bash
# Run only unit tests
python run_tests.py --unit
make test-unit
```

**Coverage:**
- FiinQuant adapter methods
- Trading strategy logic
- Cache manager operations
- Alert system components
- Data models and utilities

### Integration Tests
Test component interactions and system workflows:

```bash
# Run only integration tests
python run_tests.py --integration
make test-integration
```

**Coverage:**
- Complete trading workflows
- Real-time data processing
- Alert system integration
- Cache system integration
- Error handling and recovery

### Performance Tests
Benchmark system performance:

```bash
# Run performance benchmarks
pytest tests/ -m "benchmark"
make benchmark
```

**Coverage:**
- Strategy analysis performance
- Cache operation speed
- Data processing throughput
- Memory usage patterns

## 🎯 Test Execution Options

### By Component

```bash
# Test specific components
python run_tests.py --strategy      # Strategy tests only
python run_tests.py --cache         # Cache tests only
python run_tests.py --alert         # Alert system tests only
python run_tests.py --fiinquant     # FiinQuant adapter tests only
```

### By Speed

```bash
# Fast tests (exclude slow operations)
python run_tests.py --fast
make test-fast

# Include all tests (including slow ones)
python run_tests.py  # Default includes all
```

### By Network Dependency

```bash
# Skip network-dependent tests
python run_tests.py --no-network

# Skip Redis-dependent tests
python run_tests.py --no-redis

# Skip external service tests
python run_tests.py --no-telegram --no-email
```

### Specific Test Selection

```bash
# Run specific test file
python run_tests.py --file test_cache

# Run specific test function
python run_tests.py --test test_cache_manager

# Run tests matching pattern
pytest -k "cache and not slow"
```

## 📊 Coverage Reports

### Generate Coverage Reports

```bash
# Terminal coverage report
python run_tests.py --coverage
make test-coverage

# HTML coverage report
python run_tests.py --coverage-html
make test-html

# XML coverage report (for CI)
python run_tests.py --coverage-xml
```

### View Coverage Reports

```bash
# Open HTML report in browser
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
```

### Coverage Targets

- **Overall Coverage:** ≥ 80%
- **Core Components:** ≥ 90%
- **Critical Paths:** 100%

## 🏷️ Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Tests that take longer to run
- `@pytest.mark.network` - Tests requiring network access
- `@pytest.mark.redis` - Tests requiring Redis
- `@pytest.mark.email` - Tests involving email functionality
- `@pytest.mark.telegram` - Tests involving Telegram functionality
- `@pytest.mark.strategy` - Strategy-specific tests
- `@pytest.mark.cache` - Cache-related tests
- `@pytest.mark.benchmark` - Performance benchmark tests

### Using Markers

```bash
# Run tests with specific markers
pytest -m "unit and not slow"
pytest -m "integration and redis"
pytest -m "benchmark"

# Exclude specific markers
pytest -m "not slow and not network"
```

## 🔧 Test Configuration

### pytest.ini
Main pytest configuration file with:
- Test discovery patterns
- Default command-line options
- Coverage settings
- Marker definitions

### conftest.py
Shared test fixtures and utilities:
- Mock data generators
- Service mocks (FiinQuant, Redis, etc.)
- Test environment setup
- Common test utilities

### Environment Variables

```bash
# Set test environment
export TESTING=true
export LOG_LEVEL=DEBUG

# Redis configuration for tests
export REDIS_URL=redis://localhost:6379/1

# Disable external services in tests
export DISABLE_TELEGRAM=true
export DISABLE_EMAIL=true
```

## 🚀 Continuous Integration

### GitHub Actions
Automated testing on:
- Multiple Python versions (3.8, 3.9, 3.10, 3.11)
- Multiple operating systems (Ubuntu, Windows, macOS)
- Different test scenarios (unit, integration, security)

### Local CI Simulation

```bash
# Run full CI test suite locally
make ci-test

# Run development test workflow
make dev-test
```

## 🐛 Debugging Tests

### Verbose Output

```bash
# Verbose test output
python run_tests.py --verbose
pytest -v

# Very verbose output
pytest -vv
```

### Debug Specific Tests

```bash
# Stop on first failure
python run_tests.py --failfast
pytest -x

# Run last failed tests only
python run_tests.py --lf
pytest --lf

# Run failed tests first
python run_tests.py --ff
pytest --ff
```

### Test Output Capture

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest -l

# Full traceback
pytest --tb=long
```

## 📈 Performance Testing

### Benchmark Tests

```bash
# Run all benchmarks
pytest tests/ -m "benchmark" --benchmark-only

# Compare benchmarks
pytest tests/ -m "benchmark" --benchmark-compare

# Save benchmark results
pytest tests/ -m "benchmark" --benchmark-json=results.json
```

### Memory Profiling

```bash
# Profile memory usage
pytest tests/ --profile-mem

# Memory usage report
memory_profiler python -m pytest tests/test_strategy.py
```

## 🔒 Security Testing

### Static Security Analysis

```bash
# Run security checks
make security

# Bandit security linting
bandit -r . -f json -o security-report.json

# Check for known vulnerabilities
safety check
```

## 📝 Writing New Tests

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch

class TestYourComponent:
    """Test suite for YourComponent."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.component = YourComponent()
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = self.component.do_something()
        assert result is not None
    
    @pytest.mark.slow
    def test_expensive_operation(self):
        """Test that takes a long time to run."""
        result = self.component.expensive_operation()
        assert result.is_valid()
    
    @pytest.mark.network
    def test_network_operation(self):
        """Test that requires network access."""
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'status': 'ok'}
            result = self.component.fetch_data()
            assert result['status'] == 'ok'
```

### Best Practices

1. **Use descriptive test names** that explain what is being tested
2. **Follow AAA pattern** (Arrange, Act, Assert)
3. **Use appropriate markers** to categorize tests
4. **Mock external dependencies** to ensure test isolation
5. **Test both success and failure scenarios**
6. **Keep tests focused** on a single behavior
7. **Use fixtures** for common test data and setup

### Test Data

```python
# Use fixtures for test data
@pytest.fixture
def sample_market_data():
    return {
        'symbol': 'VIC',
        'price': 100.0,
        'volume': 1000,
        'timestamp': '2024-01-01T10:00:00Z'
    }

# Use factories for complex data
from tests.conftest import TestDataGenerator

def test_with_generated_data():
    generator = TestDataGenerator()
    signal = generator.create_trading_signal('VIC', 'BUY')
    assert signal.action == 'BUY'
```

## 🆘 Troubleshooting

### Common Issues

1. **Redis Connection Errors**
   ```bash
   # Start Redis server
   redis-server
   
   # Or skip Redis tests
   python run_tests.py --no-redis
   ```

2. **Import Errors**
   ```bash
   # Set PYTHONPATH
   export PYTHONPATH=.
   
   # Or use pytest with path
   python -m pytest tests/
   ```

3. **Slow Tests**
   ```bash
   # Skip slow tests
   python run_tests.py --fast
   
   # Run in parallel
   python run_tests.py --parallel 4
   ```

4. **Coverage Issues**
   ```bash
   # Clean coverage data
   coverage erase
   
   # Regenerate coverage
   python run_tests.py --coverage
   ```

### Getting Help

- Check test output for specific error messages
- Use `pytest --collect-only` to see available tests
- Run `python run_tests.py --help` for all options
- Check GitHub Actions logs for CI failures

## 📚 Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)