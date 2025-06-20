#!/bin/bash
# Script to test with act when Docker is running

export PATH="$HOME/.local/bin:$PATH"

echo "🐳 Testing with act (GitHub Actions locally)"
echo "=========================================="
echo ""

# Check if act is installed
if ! [ -x "$HOME/.local/bin/act" ] && ! command -v act &> /dev/null; then
    echo "❌ act is not installed"
    echo "To install: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | bash -s -- -b ~/.local/bin"
    exit 1
fi

# Check if Docker is running
if ! docker ps -q >/dev/null 2>&1; then
    echo "❌ Docker is not running"
    echo "To start Docker: sudo service docker start"
    echo ""
    echo "Alternative: Run tests directly with:"
    echo "  ./run_local_tests.sh --direct"
    exit 1
fi

echo "✅ act is installed"
echo "✅ Docker is running"
echo ""

# List available workflows
echo "📋 Available workflows:"
act -l

echo ""
echo "🚀 Running local test workflow..."
act -W .github/workflows/test-local.yml push

echo ""
echo "✨ Done!"