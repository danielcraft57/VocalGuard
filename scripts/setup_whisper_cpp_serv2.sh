#!/bin/bash
# Compat : redirige vers setup_whisper_cpp.sh (build x86 sans AVX ou ARM natif).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/setup_whisper_cpp.sh"
