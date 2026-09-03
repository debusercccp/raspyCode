#!/usr/bin/env bash
# Rimuove ricorsivamente tutte le cartelle __pycache__ (e i .pyc orfani)
# a partire dalla directory in cui viene lanciato lo script.
#
# Uso:
#   ./clean_pycache.sh            # da ~/progetti/raspyCode
#   ./clean_pycache.sh /altro/path
set -euo pipefail

TARGET_DIR="${1:-.}"

echo "Pulizia __pycache__ sotto: $(realpath "$TARGET_DIR")"

find "$TARGET_DIR" -type d -name "__pycache__" -prune -print -exec rm -rf {} +
find "$TARGET_DIR" -type f -name "*.pyc" -print -delete

echo "Fatto."
