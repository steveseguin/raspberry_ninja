#!/usr/bin/env python3
"""
Test room list parsing with actual format
"""

# Simulate the room list you showed
room_list = [
    {
        "UUID": "aec59a54-f959-4e9f-bada-84f7be2bd376",
        "streamID": "tUur6fffwt808d64"
    },
    {
        "UUID": "bbb59a54-f959-4e9f-bada-84f7be2bd376", 
        "streamID": "tUur6wt123456"
    },
    {
        "UUID": "ccc59a54-f959-4e9f-bada-84f7be2bd376"
        # This one has no streamID (not publishing)
    }
]

print("Testing room list parsing...")
print(f"Room list: {room_list}")
print("-" * 50)

# Simulate the parsing logic
streams_to_record = []
for member in room_list:
    print(f"\nChecking member: {member}")
    if 'streamID' in member:
        stream_id = member['streamID']
        uuid = member.get('UUID')
        print(f"  ✓ Found stream: {stream_id} (UUID: {uuid})")
        streams_to_record.append((stream_id, uuid))
    else:
        print(f"  - No streamID (not publishing)")

print(f"\nFound {len(streams_to_record)} streams to record")
for stream_id, uuid in streams_to_record:
    print(f"  - {stream_id} from {uuid}")