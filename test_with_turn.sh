#!/bin/bash
echo "Testing room recording with TURN server..."
echo "This uses VDO.Ninja's public TURN servers for better connectivity"
echo ""

# Run with TURN server
python3 publish.py \
    --room testroom123 \
    --record-room \
    --password false \
    --noaudio \
    --turn-server "turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478" \
    --ice-transport-policy all \
    2>&1 | grep -E "TURN|STUN|relay|Connection state:|WebRTC connected|recording started|ICE state:"