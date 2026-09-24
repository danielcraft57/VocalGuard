#!/usr/bin/env bash
# Installe Qdrant (binaire aarch64 musl) sur node15 sans Docker.
# Usage (sur node15): bash scripts/install_qdrant_node15.sh
set -euo pipefail

QDRANT_VERSION="${QDRANT_VERSION:-v1.19.1}"
INSTALL_ROOT="${INSTALL_ROOT:-/opt/qdrant}"
STORAGE_ROOT="${STORAGE_ROOT:-/var/lib/qdrant/storage}"
ASSET="qdrant-aarch64-unknown-linux-musl.tar.gz"
URL="https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/${ASSET}"

echo "Install Qdrant ${QDRANT_VERSION} -> ${INSTALL_ROOT}"
sudo mkdir -p "${INSTALL_ROOT}/bin" "${INSTALL_ROOT}/config" "${STORAGE_ROOT}"
sudo chown -R "$(whoami):$(whoami)" "${INSTALL_ROOT}" "${STORAGE_ROOT%/*}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL -o "${tmpdir}/${ASSET}" "$URL"
tar -xzf "${tmpdir}/${ASSET}" -C "${INSTALL_ROOT}/bin"
chmod +x "${INSTALL_ROOT}/bin/qdrant"
"${INSTALL_ROOT}/bin/qdrant" --version

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "${SCRIPT_DIR}/qdrant/config.yaml" ]]; then
  cp "${SCRIPT_DIR}/qdrant/config.yaml" "${INSTALL_ROOT}/config/config.yaml"
fi
if [[ -f "${SCRIPT_DIR}/systemd/qdrant.service" ]]; then
  sudo cp "${SCRIPT_DIR}/systemd/qdrant.service" /etc/systemd/system/qdrant.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now qdrant
fi

sleep 1
curl -fsS "http://127.0.0.1:6333/" | head -c 200
echo
echo "Qdrant OK. Dashboard: http://$(hostname -I | awk '{print $1}'):6333/dashboard"
