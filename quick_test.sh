#!/bin/bash
echo "Testing room recording without pre-added transceivers..."
timeout 20 python3 publish.py --room testroom123 --record notrans_test --record-room --password false --noaudio 2>&1 | grep -E "(WebRTC element created|Recording started|Connection.*FAILED|ICE.*NEW)" || echo "Test completed"