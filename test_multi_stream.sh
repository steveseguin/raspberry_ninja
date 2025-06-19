#\!/bin/bash
# Start multiple recording instances for different streams

# Record stream 1
python3 publish.py --room testroom123 --record stream1 --password false --noaudio &
PID1=$\!

# Record stream 2  
python3 publish.py --room testroom123 --record stream2 --password false --noaudio &
PID2=$\!

# Record stream 3
python3 publish.py --room testroom123 --record stream3 --password false --noaudio &
PID3=$\!

echo "Started recorders with PIDs: $PID1, $PID2, $PID3"
echo "Press Ctrl+C to stop all recorders"

# Wait and handle cleanup
trap "kill $PID1 $PID2 $PID3 2>/dev/null" EXIT
wait
