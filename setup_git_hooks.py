#!/usr/bin/env python3
"""
Setup Git hooks for cross-platform testing
Works on Windows, WSL, and Linux
"""
import os
import sys
import platform
import subprocess
import shutil

def setup_git_hooks():
    """Setup pre-push hooks for the current platform"""
    
    git_dir = ".git"
    hooks_dir = os.path.join(git_dir, "hooks")
    
    if not os.path.exists(git_dir):
        print("❌ Error: Not in a git repository")
        return False
        
    if not os.path.exists(hooks_dir):
        os.makedirs(hooks_dir)
        
    # Determine platform
    system = platform.system()
    print(f"🖥️  Detected platform: {system}")
    
    # Copy appropriate hook
    if system == "Windows":
        # On Windows, Git Bash will still use the bash script
        # But we'll also set up the .bat file as backup
        pre_push_src = ".git/hooks/pre-push"
        pre_push_bat_src = ".git/hooks/pre-push.bat"
        
        print("📝 Setting up Windows Git hooks...")
        
        # Make sure both exist
        if os.path.exists(pre_push_src):
            print("✅ Bash pre-push hook already exists")
        
        if os.path.exists(pre_push_bat_src):
            print("✅ Batch pre-push hook already exists")
            
    else:
        # Linux/WSL
        pre_push_src = ".git/hooks/pre-push"
        
        if os.path.exists(pre_push_src):
            # Make it executable
            try:
                os.chmod(pre_push_src, 0o755)
                print("✅ Made pre-push hook executable")
            except:
                print("⚠️  Could not make hook executable - you may need to run: chmod +x .git/hooks/pre-push")
    
    # Test Python availability
    print("\n🐍 Testing Python setup...")
    
    # Try to run the basic test
    try:
        result = subprocess.run(
            [sys.executable, "test_basic_functionality.py"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Python tests are working")
        else:
            print("⚠️  Python tests failed - check your Python environment")
    except Exception as e:
        print(f"❌ Error running tests: {e}")
    
    # Check for pytest
    try:
        subprocess.run([sys.executable, "-m", "pytest", "--version"], 
                      capture_output=True, check=True)
        print("✅ pytest is installed")
    except:
        print("⚠️  pytest not found - install with: pip install pytest pytest-asyncio")
    
    print("\n✨ Git hooks setup complete!")
    print("\nThe pre-push hook will run automatically when you:")
    print("  - git push (from any environment)")
    print("\nTo test manually:")
    print("  - Windows: python test_basic_functionality.py")
    print("  - WSL/Linux: ./run_local_tests.sh --quick")
    
    return True

if __name__ == "__main__":
    setup_git_hooks()