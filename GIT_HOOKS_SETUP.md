# Git Hooks Setup - Auto-run Tests on Push

## 🎯 Overview

The pre-push hook automatically runs tests before you push to GitHub, regardless of whether you're using:
- Windows Command Prompt
- Windows PowerShell  
- Git Bash on Windows
- WSL (Windows Subsystem for Linux)
- Linux/Mac

## 🔧 Setup Instructions

### Option 1: Already Set Up!
The hooks are already installed in `.git/hooks/pre-push`. They should work automatically.

### Option 2: Verify Setup
Run this from any environment:
```bash
python setup_git_hooks.py
```

## 📋 What Happens When You Push

When you run `git push` from ANY environment:

1. **Basic Tests Run First** (Always)
   - `test_basic_functionality.py` must pass
   - If it fails, push is blocked

2. **Additional Tests** (When pushing to main/develop)
   - More comprehensive tests run
   - Failures are warnings only (non-blocking)

3. **Code Quality Checks**
   - Checks for print statements in tests
   - Counts TODO comments

## 🖥️ Platform-Specific Behavior

### Windows Command Prompt / PowerShell
```cmd
C:\Users\steve\Code\raspberry_ninja> git push origin main
🔍 Running pre-push tests...
============================
✅ Basic tests passed
✅ Pre-push checks completed
Proceeding with push...
```

### WSL / Linux
```bash
$ git push origin main
🔍 Running pre-push tests...
============================
✅ Basic tests passed
✅ Pre-push checks completed
Proceeding with push...
```

## 🛠️ Troubleshooting

### "Python not found"
- **Windows**: Make sure Python is in PATH
- **WSL**: The hook automatically uses `python3`

### "pytest not found"
- **Windows**: `pip install pytest pytest-asyncio`
- **WSL**: `pip3 install --user pytest pytest-asyncio`

### Hook not running
- Check if `.git/hooks/pre-push` exists
- On Linux/WSL: `chmod +x .git/hooks/pre-push`

### Tests failing
- Run tests manually first:
  - **Windows**: `python test_basic_functionality.py`
  - **WSL**: `./run_local_tests.sh --quick`

## 🚀 Manual Testing

### Before pushing, you can test manually:

**Windows Command Prompt:**
```cmd
python test_basic_functionality.py
python -m pytest test_multiple_webrtc_connections.py -v
```

**WSL/Linux:**
```bash
./run_local_tests.sh --quick
```

## ⚙️ Configuration

The hook checks for protected branches (main, develop) and runs more tests.

To modify this behavior, edit `.git/hooks/pre-push`:
```bash
protected_branches="main develop feature/important"
```

## 📊 Example Output

### Successful Push:
```
🔍 Running pre-push tests...
============================
1️⃣ Running basic functionality tests...
✅ Basic tests passed
3️⃣ Running code quality checks...
⚠️ Found 5 TODO comments
✅ Pre-push checks completed
Proceeding with push...

Enumerating objects: 5, done.
Counting objects: 100% (5/5), done.
Writing objects: 100% (3/3), 1.28 KiB | 1.28 MiB/s, done.
To github.com:user/repo.git
   abc123..def456  main -> main
```

### Failed Push:
```
🔍 Running pre-push tests...
============================
1️⃣ Running basic functionality tests...
❌ Basic tests failed
See details in /tmp/test_results.log

Push aborted. Fix the tests before pushing.
```

## 🎉 Benefits

1. **Catches issues early** - Before they reach GitHub
2. **Works everywhere** - Windows, WSL, Linux
3. **Fast feedback** - Basic tests run in seconds
4. **Protects main branch** - Extra checks for important branches
5. **Non-intrusive** - Only blocks on critical failures

## 💡 Tips

- Keep `test_basic_functionality.py` fast and reliable
- Run `./run_local_tests.sh --quick` before important pushes
- The hook is just a safety net - test thoroughly during development
- GitHub Actions will run the full test suite after push