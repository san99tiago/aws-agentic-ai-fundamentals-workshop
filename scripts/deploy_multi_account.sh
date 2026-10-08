#!/usr/bin/env bash
# Deploy the foundation stack to MANY workshop accounts (one AWS CLI profile per account).
#   ./scripts/deploy_multi_account.sh team01 team02 team03
# The portal is deployed only once (first profile) unless DEPLOY_FRONTEND_ALL=true.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ $# -gt 0 ]] || { echo "Usage: $0 <aws-profile> [<aws-profile> ...]"; exit 1; }
FIRST=true
for PROFILE in "$@"; do
  echo "════════ ${PROFILE} ════════"
  if [[ "$FIRST" == "true" || "${DEPLOY_FRONTEND_ALL:-false}" == "true" ]]; then FRONT=true; else FRONT=false; fi
  AWS_PROFILE="$PROFILE" DEPLOY_FRONTEND="$FRONT" "$ROOT/scripts/deploy.sh" || echo "⚠️ ${PROFILE} failed, continuing"
  FIRST=false
done
