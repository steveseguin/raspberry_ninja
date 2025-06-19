# Testing Guide for Raspberry Ninja

This guide explains how to run tests for the Raspberry Ninja project, both locally and in CI/CD environments.

## 🚀 Quick Start

### Running Tests Locally

1. **Basic Tests** (Always passing, good for sanity check):
   ```bash
   python3 test_basic_functionality.py
   ```

2. **All Tests** (Using the test runner):
   ```bash
   python3 run_all_tests.py
   ```

3. **Specific Test Suite**:
   ```bash
   # With pytest
   python3 -m pytest test_multiple_webrtc_connections.py -v
   
   # Without pytest
   python3 test_multiple_webrtc_connections.py
   ```

### Using the Local Test Runner

We provide a convenient test runner script:

```bash
# Run with act (if installed)
./run_local_tests.sh

# Run tests directly
./run_local_tests.sh --direct

# Run quick smoke tests
./run_local_tests.sh --quick
```

## 🐳 Running Tests with Act

[Act](https://github.com/nektos/act) allows you to run GitHub Actions locally.

### Installation

```bash
# Install act
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

### Configuration

The project includes an `.actrc` file with optimized settings:
- Uses smaller Docker images for faster execution
- Reuses containers between runs
- Uses host network for better performance

### Running Tests with Act

```bash
# Run all workflows
act

# Run specific workflow
act -W .github/workflows/test-local.yml

# Run with specific event
act push
```

## 📋 Test Suites

### 1. Basic Functionality Tests (`test_basic_functionality.py`)
- Recording file creation
- Filename format validation
- Codec detection
- Session management
- Error handling

**Status**: ✅ All tests passing

### 2. Multiple WebRTC Connections (`test_multiple_webrtc_connections.py`)
- Concurrent connection creation
- Connection isolation
- Resource cleanup
- Session management
- Recording pipelines

**Status**: ⚠️ Some tests require GStreamer mocking fixes

### 3. Concurrent Stream Handling (`test_concurrent_stream_handling.py`)
- Stream buffering
- Bandwidth management
- Quality adaptation
- A/V synchronization

**Status**: 🔧 Advanced tests, require implementation

### 4. Session Management (`test_session_management_multiple_peers.py`)
- Session lifecycle
- UUID mapping
- State transitions
- Persistence

**Status**: ✅ Core functionality passing

### 5. Room Recording Integration (`test_room_recording_integration.py`)
- Multi-stream recording
- Dynamic room membership
- Resource utilization
- Error recovery

**Status**: 🔧 Integration tests, require full setup

### 6. Edge Cases and Errors (`test_edge_cases_and_errors.py`)
- Maximum connections
- Invalid inputs
- Memory leaks
- Race conditions

**Status**: 🔧 Comprehensive error testing

## 🔄 CI/CD Integration

### GitHub Actions

The project includes GitHub Actions workflows:

1. **Main Test Workflow** (`.github/workflows/test.yml`):
   - Runs on push to main/develop
   - Tests multiple Python versions
   - Includes coverage reporting
   - Runs linting and security checks

2. **Local Test Workflow** (`.github/workflows/test-local.yml`):
   - Optimized for local testing with act
   - Minimal dependencies
   - Quick feedback

### Pre-push Hook

Install the pre-push hook to run tests before pushing:

```bash
# The hook is already in .git/hooks/pre-push
# Make it executable (if needed)
chmod +x .git/hooks/pre-push
```

## 🛠️ Test Dependencies

### Required Python Packages

```bash
pip install pytest pytest-asyncio pytest-cov psutil
```

### System Dependencies (for full tests)

```bash
# Ubuntu/Debian
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    python3-gi \
    python3-gi-cairo
```

## 📊 Test Reports

Test results are saved in multiple formats:

1. **JSON Report** (`test_report.json`):
   - Detailed test results
   - Timing information
   - Failure details

2. **Text Report** (`test_report.txt`):
   - Human-readable summary
   - Recommendations
   - Quick overview

3. **Coverage Report** (when using pytest-cov):
   - Code coverage statistics
   - Uncovered lines
   - Coverage trends

## 🔍 Debugging Failed Tests

1. **Run with verbose output**:
   ```bash
   python3 -m pytest test_name.py -v -s
   ```

2. **Run specific test**:
   ```bash
   python3 -m pytest test_file.py::TestClass::test_method
   ```

3. **Enable traceback**:
   ```bash
   python3 -m pytest test_name.py --tb=long
   ```

4. **Check test logs**:
   ```bash
   # Test outputs are in test_results/ directory
   cat test_results/unit_tests.log
   ```

## 🎯 Best Practices

1. **Run basic tests frequently** - They're fast and catch common issues
2. **Use the pre-push hook** - Prevents pushing broken code
3. **Run full test suite before PRs** - Ensures comprehensive coverage
4. **Keep tests fast** - Mock external dependencies
5. **Write new tests for new features** - Maintain coverage

## 🚧 Known Issues

1. **GStreamer Mocking**: Some tests require proper GStreamer mocking
2. **Async Tests**: Ensure proper event loop handling
3. **File System Tests**: May fail on read-only file systems

## 📈 Improving Tests

To add new tests:

1. Create a test file following the pattern `test_*.py`
2. Use unittest or pytest framework
3. Mock external dependencies
4. Add to the test runner
5. Update this documentation

## 🆘 Getting Help

If tests are failing:

1. Check the test output for specific errors
2. Ensure all dependencies are installed
3. Check if the issue is environment-specific
4. Look for recent changes that might have broken tests
5. Ask for help with specific error messages