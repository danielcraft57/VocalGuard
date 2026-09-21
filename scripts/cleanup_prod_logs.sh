#!/usr/bin/env bash
# Nettoyage one-shot des logs prod VocalGuard (Pi) : archive + truncate + logrotate.
#
# Usage sur le Pi :
#   APP_DIR=/opt/vocalguard bash scripts/cleanup_prod_logs.sh
#
# Variables :
#   MIN_SIZE_MB=10        Seuil (Mo) au-dela duquel un .log est traite
#   SKIP_ARCHIVE=1        Tronque sans archiver (disque tres plein)
#   KEEP_ARCHIVE_DAYS=7   Supprime les archives pre-cleanup plus vieilles
#   INSTALL_LOGROTATE=1   Installe logrotate (defaut: 1)
#   FORCE_LOGROTATE=1     Lance logrotate -f apres install (defaut: 1)
#   DRY_RUN=1             Affiche sans modifier
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
LOG_DIR="$APP_DIR/logs"
MIN_SIZE_MB="${MIN_SIZE_MB:-10}"
KEEP_ARCHIVE_DAYS="${KEEP_ARCHIVE_DAYS:-7}"
INSTALL_LOGROTATE="${INSTALL_LOGROTATE:-1}"
FORCE_LOGROTATE="${FORCE_LOGROTATE:-1}"
SKIP_ARCHIVE="${SKIP_ARCHIVE:-0}"
DRY_RUN="${DRY_RUN:-0}"

human_size() {
  local bytes="$1"
  if [ "$bytes" -ge 1073741824 ]; then
    printf "%.1f Go" "$(awk "BEGIN {print $bytes/1073741824}")"
  elif [ "$bytes" -ge 1048576 ]; then
    printf "%.1f Mo" "$(awk "BEGIN {print $bytes/1048576}")"
  elif [ "$bytes" -ge 1024 ]; then
    printf "%.1f Ko" "$(awk "BEGIN {print $bytes/1024}")"
  else
    printf "%s o" "$bytes"
  fi
}

if [ ! -d "$LOG_DIR" ]; then
  echo "Dossier logs introuvable: $LOG_DIR"
  exit 1
fi

min_bytes=$((MIN_SIZE_MB * 1024 * 1024))
stamp="$(date +%Y%m%d-%H%M%S)"
archive_dir="$LOG_DIR/archive/pre-cleanup-$stamp"

echo "=== VocalGuard - nettoyage logs prod ==="
echo "APP_DIR=$APP_DIR"
echo "Seuil: ${MIN_SIZE_MB} Mo (SKIP_ARCHIVE=$SKIP_ARCHIVE, DRY_RUN=$DRY_RUN)"
echo ""

total_before=0
targets=()

while IFS= read -r -d '' file; do
  size="$(stat -c '%s' "$file" 2>/dev/null || echo 0)"
  total_before=$((total_before + size))
  base="$(basename "$file")"
  if [ "$size" -ge "$min_bytes" ]; then
    echo "  [A TRAITER] $base -> $(human_size "$size")"
    targets+=("$file")
  else
    echo "  [ok]        $base -> $(human_size "$size")"
  fi
done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -print0)

echo ""
echo "Total logs actifs: $(human_size "$total_before")"

if [ "${#targets[@]}" -eq 0 ]; then
  echo "Aucun fichier au-dessus du seuil."
else
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY_RUN: rien modifie."
  else
    if [ "$SKIP_ARCHIVE" != "1" ]; then
      mkdir -p "$archive_dir"
      echo "Archives -> $archive_dir"
    fi

    for file in "${targets[@]}"; do
      base="$(basename "$file")"
      size="$(stat -c '%s' "$file")"
      if [ "$SKIP_ARCHIVE" = "1" ]; then
        echo "Truncate $base ($(human_size "$size")) sans archive"
        : >"$file"
      else
        echo "Archive + truncate $base ($(human_size "$size"))"
        # Copie puis truncate avant gzip : evite "file size changed while zipping" (systemd ecrit encore).
        cp "$file" "$archive_dir/$base"
        : >"$file"
        gzip "$archive_dir/$base"
      fi
    done
  fi
fi

if [ "$DRY_RUN" != "1" ] && [ "$KEEP_ARCHIVE_DAYS" -gt 0 ] && [ -d "$LOG_DIR/archive" ]; then
  echo ""
  echo "Suppression archives pre-cleanup > ${KEEP_ARCHIVE_DAYS} jours..."
  find "$LOG_DIR/archive" -mindepth 1 -maxdepth 1 -type d -name 'pre-cleanup-*' -mtime "+$KEEP_ARCHIVE_DAYS" -exec rm -rf {} +
fi

if [ "$INSTALL_LOGROTATE" = "1" ] && [ "$DRY_RUN" != "1" ]; then
  echo ""
  install_script="$APP_DIR/scripts/install_logrotate.sh"
  if [ -f "$install_script" ]; then
    echo "Installation logrotate..."
    APP_DIR="$APP_DIR" bash "$install_script"
    if [ "$FORCE_LOGROTATE" = "1" ] && [ -f /etc/logrotate.d/vocalguard ]; then
      echo "Rotation forcee (logrotate -f)..."
      sudo logrotate -f /etc/logrotate.d/vocalguard
    fi
  else
    echo "WARN: $install_script absent (deploy d'abord ?)"
  fi
fi

if [ "$DRY_RUN" != "1" ]; then
  echo ""
  echo "Etat apres nettoyage:"
  du -sh "$LOG_DIR" 2>/dev/null || true
  ls -lh "$LOG_DIR"/*.log 2>/dev/null || true
fi

echo ""
echo "Termine."
