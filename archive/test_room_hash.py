#!/usr/bin/env python3
"""
Test if room names are being hashed
"""

import sys
sys.path.insert(0, '.')

from publish import generateHash

# Test room name
room = "testroom123"

# Check if hash is generated
print(f"Room name: {room}")

# The issue might be that test mode uses a password
# Let's check what happens with password
password = "someEncryptionKey123"
salt = "vdo.ninja"

if password:
    room_hash = generateHash(room + password + salt, 16)
    print(f"Room hash with password: {room_hash}")
    
# Without password
print(f"Room without password: {room}")

# Check the test flag behavior
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--test', action='store_true')
parser.add_argument('--room', type=str)
parser.add_argument('--password', type=str)

# Simulate test mode
args = parser.parse_args(['--test', '--room', room])
print(f"\nTest mode args:")
print(f"  test: {args.test}")
print(f"  room: {args.room}")
print(f"  password: {args.password}")

# Check if test mode sets a default password
print("\nChecking if test mode affects room...")

# Read publish.py to find test mode handling
with open('publish.py', 'r') as f:
    content = f.read()
    
# Look for test mode password setting
import re
matches = re.findall(r'args\.test.*password|test.*someEncryptionKey', content, re.IGNORECASE)
if matches:
    print("Found test mode password references:")
    for m in matches[:5]:
        print(f"  {m}")
else:
    print("No test mode password found")