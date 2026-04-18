#!/usr/bin/env bash
# Start the frontend dev server using Node 20 from nvm.
# Usage: bash start.sh
set -e

NODE20="$HOME/.nvm/versions/node/v20.20.2/bin/node"

if [ ! -f "$NODE20" ]; then
  echo "Node 20 not found at $NODE20"
  echo "Run: export NVM_DIR=\"\$HOME/.nvm\" && source \"\$NVM_DIR/nvm.sh\" && nvm install 20"
  exit 1
fi

echo "Using node: $($NODE20 --version)"
exec "$NODE20" node_modules/.bin/vite
