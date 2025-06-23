#!/usr/bin/env python3
"""Check splitmuxsink pad templates"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

# Create splitmuxsink
splitmuxsink = Gst.ElementFactory.make("splitmuxsink", None)

# List all pad templates
factory = splitmuxsink.get_factory()
print("Pad templates for splitmuxsink:")
for i in range(factory.get_num_pad_templates()):
    template = factory.get_static_pad_templates()[i]
    print(f"  {template.name_template} ({template.direction.value_nick}) - {template.presence.value_nick}")

# Try different approaches
print("\nTrying to request pads:")

# Try video and audio names
for name in ['video', 'audio', 'sink', 'sink_%u', 'video_%u', 'audio_%u']:
    pad = splitmuxsink.request_pad_simple(name)
    if pad:
        print(f"  ✓ Successfully got pad with '{name}': {pad.get_name()}")
    else:
        print(f"  ✗ Failed with '{name}'")

# Check if splitmuxsink needs a muxer set first
print("\nSetting muxer property and trying again:")
muxer = Gst.ElementFactory.make("mpegtsmux", None)
splitmuxsink.set_property("muxer", muxer)

for name in ['video', 'audio', 'sink_%u']:
    pad = splitmuxsink.request_pad_simple(name)
    if pad:
        print(f"  ✓ Successfully got pad with '{name}': {pad.get_name()}")
    else:
        print(f"  ✗ Failed with '{name}'")