# Pull Request Attribution

This file documents merged pull requests and their contributors to ensure proper credit.

## PR #42 - Audio Recording and Transcription Service

- **Author**: papiche (@papiche)
- **Date**: January 2025
- **Description**: Added `record.py` - a standalone microservice for audio recording and transcription using Whisper AI
- **Files contributed**:
  - `record.py` - Main service implementation
  - `templates/index.html` - Web interface
  - `templates/recording.html` - Recording management UI
  - `templates/record.service.tpl` - Systemd service template
  - `setup.ninja_record.systemd.sh` - Service installation script
  - `stt/.readme` - Transcription directory placeholder
- **Integration commits**:
  - 330e531: feat: Add record.py audio recording and transcription service from PR #42
  - 31e845b: docs: Add comprehensive documentation for record.py audio recording service
  - b930f2e: docs: Add record.py section to table of contents
  - 75a0e04: docs: Add CONTRIBUTORS.md to properly credit papiche for record.py

Thank you papiche for this valuable contribution!