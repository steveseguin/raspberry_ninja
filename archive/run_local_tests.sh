#!/bin/bash
# Script to run tests locally using act or directly

# Add local bin to PATH for pytest and act
export PATH="$HOME/.local/bin:$PATH"

# Ensure we can find pytest module
export PYTHONPATH="$HOME/.local/lib/python3.10/site-packages:$PYTHONPATH"

echo "🧪 Raspberry Ninja Local Test Runner"
echo "===================================="

# Check if act is installed
if [ -x "$HOME/.local/bin/act" ] || command -v act &> /dev/null; then
    echo "✓ act is installed"
    USE_ACT=true
else
    echo "⚠ act is not installed. Install with: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash"
    echo "  Falling back to direct test execution..."
    USE_ACT=false
fi

# Function to run tests directly
run_direct_tests() {
    echo ""
    echo "📋 Running tests directly..."
    echo ""
    
    # Create test results directory
    mkdir -p test_results
    
    # Run unit tests
    echo "1️⃣ Running unit tests..."
    pytest test_multiple_webrtc_connections.py -v --tb=short 2>&1 | tee test_results/unit_tests.log || true
    
    echo ""
    echo "2️⃣ Running concurrent stream tests..."
    pytest test_concurrent_stream_handling.py -v --tb=short 2>&1 | tee test_results/concurrent_tests.log || true
    
    echo ""
    echo "3️⃣ Running session management tests..."  
    pytest test_session_management_multiple_peers.py -v --tb=short 2>&1 | tee test_results/session_tests.log || true
    
    echo ""
    echo "4️⃣ Running edge case tests..."
    pytest test_edge_cases_and_errors.py -v --tb=short 2>&1 | tee test_results/edge_case_tests.log || true
    
    # Generate summary
    echo ""
    echo "📊 Test Summary"
    echo "==============="
    
    for log in test_results/*.log; do
        if [ -f "$log" ]; then
            echo -n "$(basename $log): "
            if grep -q "FAILED" "$log"; then
                echo "❌ FAILED"
            elif grep -q "passed" "$log"; then
                echo "✅ PASSED"
            else
                echo "⚠️ UNKNOWN"
            fi
        fi
    done
}

# Function to run tests with act
run_act_tests() {
    echo ""
    echo "🐳 Running tests with act..."
    echo ""
    
    # Run the local test workflow
    act -W .github/workflows/test-local.yml push
}

# Main execution
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --direct    Force direct test execution (without act)"
    echo "  --act       Force test execution with act"
    echo "  --quick     Run only quick smoke tests"
    echo "  --help      Show this help message"
    exit 0
fi

if [ "$1" == "--direct" ]; then
    run_direct_tests
elif [ "$1" == "--act" ]; then
    if [ "$USE_ACT" == "true" ]; then
        run_act_tests
    else
        echo "❌ act is not installed. Cannot use --act option."
        exit 1
    fi
elif [ "$1" == "--quick" ]; then
    echo "🚀 Running quick smoke tests..."
    
    # Run basic functionality tests (always pass)
    echo ""
    echo "Testing basic functionality..."
    pytest test_basic_functionality.py -v --tb=short
    
    # Run a few specific tests that should pass
    echo ""
    echo "Testing connection isolation..."
    pytest test_multiple_webrtc_connections.py::TestMultipleWebRTCConnections::test_connection_isolation -v
    
    echo ""
    echo "Testing basic session management..."
    pytest test_session_management_multiple_peers.py::test_basic_session_management -v
else
    # Default behavior
    if [ "$USE_ACT" == "true" ]; then
        run_act_tests
    else
        run_direct_tests
    fi
fi

echo ""
echo "✨ Test run complete!"