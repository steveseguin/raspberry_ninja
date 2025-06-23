#!/bin/bash
# Quick HLS test script

echo "Starting HLS test..."
python3 publish.py --record-room --hls --room asdfasfsdfgasdf --debug 2>&1 | (
    timeout 30 grep -E "AttributeError|connected to HLS|segment created|New HLS|ERROR" || true
) &
PID=$!

sleep 35
kill $PID 2>/dev/null

echo -e "\nChecking for new segments:"
find . -name "asdfasfsdfgasdf_*.ts" -mmin -1 -ls 2>/dev/null | tail -5

echo -e "\nChecking segment contents:"
LATEST=$(find . -name "asdfasfsdfgasdf_*.ts" -mmin -1 2>/dev/null | tail -1)
if [ -n "$LATEST" ]; then
    ffprobe -v quiet -show_streams "$LATEST" 2>&1 | grep codec_type | sort | uniq -c
fi