#!/bin/bash
# Installe whisper.cpp (cli + server) + modele ggml-small-q5_1 pour le service STT.
# ARM (Pi) : build natif NEON. x86 sans AVX : flags SSE uniquement (ex. T4400).
set -euo pipefail

ROOT="${STT_BASE_PATH:-/opt/vocalguard-stt}"
SRC="$ROOT/whisper.cpp"
MODELS="$ROOT/whisper-models"
MODEL_NAME="${STT_WHISPER_GGML_NAME:-ggml-base-q5_1.bin}"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_NAME}"
ARCH="$(uname -m)"
JOBS="$(nproc 2>/dev/null || echo 2)"
CLI_BIN="$SRC/build/bin/whisper-cli"
SERVER_BIN="$SRC/build/bin/whisper-server"

mkdir -p "$ROOT" "$MODELS"
cd "$ROOT"

if ! command -v cmake >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cmake g++ make git curl
fi

if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$SRC"
fi

cd "$SRC"
NEED_BUILD=0
if [ ! -x "$CLI_BIN" ]; then NEED_BUILD=1; fi
if [ ! -x "$SERVER_BIN" ]; then NEED_BUILD=1; fi

if [ "$NEED_BUILD" = "1" ]; then
  if [ ! -f "$SRC/build/CMakeCache.txt" ]; then
    if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
      cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DGGML_AVX=OFF \
        -DGGML_AVX2=OFF \
        -DGGML_AVX512=OFF \
        -DGGML_FMA=OFF \
        -DGGML_F16C=OFF \
        -DGGML_SSE42=OFF \
        -DGGML_BMI2=OFF \
        -DCMAKE_C_FLAGS="-msse2 -mssse3" \
        -DCMAKE_CXX_FLAGS="-msse2 -mssse3"
    else
      cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=ON
    fi
  fi
  cmake --build build -j"$JOBS" --config Release --target whisper-cli
  cmake --build build -j"$JOBS" --config Release --target whisper-server
fi

if [ ! -f "$MODELS/$MODEL_NAME" ]; then
  curl -L --fail -o "$MODELS/$MODEL_NAME" "$MODEL_URL"
fi

test -x "$CLI_BIN"
test -x "$SERVER_BIN"
test -f "$MODELS/$MODEL_NAME"
echo "WHISPER_CPP_OK arch=$ARCH cli=$CLI_BIN server=$SERVER_BIN model=$MODELS/$MODEL_NAME"
