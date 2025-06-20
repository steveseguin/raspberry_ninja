#!/bin/bash

# Clean up old files
rm -f *.mkv *.webm *.mp4 *.ts

ROOM="testrecordingroom_$$"
echo "Using room: $ROOM"

# Start a publisher with test source
echo "Starting publisher..."
python3 publish.py --room "$ROOM" --streamid "test_publisher" --test --password false > publisher.log 2>&1 &
PUBLISHER_PID=$!

# Wait for publisher to connect
echo "Waiting for publisher to connect..."
sleep 10

# Start recorder
echo -e "\nStarting recorder..."
timeout 30 python3 publish.py --room "$ROOM" --record-room --password false 2>&1 | tee recorder.log &
RECORDER_PID=$!

# Let it run for a bit
echo -e "\nRecording for 25 seconds..."
sleep 25

# Stop processes
echo -e "\nStopping processes..."
kill $RECORDER_PID 2>/dev/null
kill $PUBLISHER_PID 2>/dev/null

# Check results
echo -e "\n\nResults:"
echo "Files created:"
ls -la *.mkv *.webm *.mp4 *.ts 2>/dev/null

echo -e "\n\nPad messages:"
grep -i "pad.*added\|new pad" recorder.log | head -10

echo -e "\n\nPublisher status:"
tail -20 publisher.log | grep -E "(View at|Stream Ready|connected)"