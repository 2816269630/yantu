#!/usr/bin/env bash
set -euo pipefail
deployment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$deployment_dir"
exec docker compose --env-file plane.env \
  -f docker-compose.yaml -f docker-compose.yantu.yml -f docker-compose.vpn.yml "$@"
