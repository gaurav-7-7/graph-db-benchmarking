#!/usr/bin/env bash
# =============================================================================
# data/download.sh — Download and prepare the SNAP soc-Pokec dataset
# =============================================================================
# Usage: bash data/download.sh
# Downloads soc-pokec-relationships.txt.gz and soc-pokec-profiles.txt.gz
# from the Stanford SNAP repository, then decompresses them into data/raw/.
#
# After this, run: python data/sample.py
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_DIR="$SCRIPT_DIR/raw"

mkdir -p "$RAW_DIR"

RELATIONSHIPS_URL="https://snap.stanford.edu/data/soc-pokec-relationships.txt.gz"
PROFILES_URL="https://snap.stanford.edu/data/soc-pokec-profiles.txt.gz"

echo "==> Downloading soc-pokec-relationships.txt.gz ..."
curl -L --progress-bar -o "$RAW_DIR/soc-pokec-relationships.txt.gz" "$RELATIONSHIPS_URL"

echo "==> Downloading soc-pokec-profiles.txt.gz ..."
curl -L --progress-bar -o "$RAW_DIR/soc-pokec-profiles.txt.gz" "$PROFILES_URL"

echo "==> Decompressing ..."
gunzip -kf "$RAW_DIR/soc-pokec-relationships.txt.gz"
gunzip -kf "$RAW_DIR/soc-pokec-profiles.txt.gz"

echo ""
echo "==> Done. Raw files:"
ls -lh "$RAW_DIR"/*.txt

echo ""
echo "Next step: python data/sample.py"
