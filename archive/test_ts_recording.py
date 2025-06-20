import sys
import subprocess

# Monkey patch to enable test mode
cmd = [sys.executable, "publish.py", "--room", "testroom123999999999", "--record-room", "--password", "false"]

# Run with environment variable to enable test mode
import os
os.environ['TEST_MODE'] = '1'
os.environ['MUX_FORMAT'] = 'ts'

# Run the command
subprocess.run(cmd)
