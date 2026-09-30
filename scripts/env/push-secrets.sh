#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" != "production" || "$#" != 1 ]]; then
  printf '%s\n' 'Usage: scripts/env/push-secrets.sh production' >&2
  exit 1
fi
cd "$(dirname "$0")/../.."
exec pnpm env:push-secrets production
