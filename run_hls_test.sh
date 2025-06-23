#!/bin/bash
# HLS test runner

# Kill any existing processes
pkill -f "publish.py.*finaltest" 2>/dev/null

# Clean up old test files
rm -f finaltest_*.ts finaltest_*.m3u8 2>/dev/null

echo "Starting HLS test with room 'finaltest'..."

# Run in background
python3 publish.py --record-room --hls --room finaltest --debug > hls_finaltest.log 2>&1 &
PID=$!

echo "Process $PID started, monitoring for 30 seconds..."

# Monitor for 30 seconds
for i in {1..30}; do
    sleep 1
    # Check if process is still running
    if ! kill -0 $PID 2>/dev/null; then
        echo "Process ended early at $i seconds"
        break
    fi
    # Check for segments every 5 seconds
    if [ $((i % 5)) -eq 0 ]; then
        COUNT=$(ls finaltest_*.ts 2>/dev/null | wc -l)
        echo "  $i seconds: $COUNT segments"
    fi
done

# Kill process
kill $PID 2>/dev/null

echo -e "\nFinal results:"
echo "Segments: $(ls finaltest_*.ts 2>/dev/null | wc -l)"
echo "Playlists: $(ls finaltest_*.m3u8 2>/dev/null | wc -l)"

# Check a segment if any exist
if ls finaltest_*.ts >/dev/null 2>&1; then
    FIRST=$(ls finaltest_*.ts | head -1)
    echo -e "\nChecking $FIRST:"
    ffprobe -v quiet -show_streams "$FIRST" 2>&1 | grep codec_type | sort | uniq -c
fi

# Show key log messages
echo -e "\nKey messages from log:"
grep -E "connected to splitmuxsink|Splitmuxsink state|segment created|ERROR" hls_finaltest.log | tail -10