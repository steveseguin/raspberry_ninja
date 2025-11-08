#!/usr/bin/env bash
set -euo pipefail

# Lightweight entrypoint for updating the Jetson media toolchain without the legacy
# distro-upgrade steps. This simply forwards to installer.sh with the relevant
# environment defaults applied so the build flow stays in one place.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export INCLUDE_DISTRO_UPGRADE=${INCLUDE_DISTRO_UPGRADE:-0}
exec "${SCRIPT_DIR}/installer.sh" "$@"
