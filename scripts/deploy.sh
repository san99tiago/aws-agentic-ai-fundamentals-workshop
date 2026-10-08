#!/usr/bin/env bash
# Deploy the workshop (foundation + portal) to the CURRENT AWS credentials/profile.
#   ./scripts/deploy.sh                 # uses .env
#   DEPLOY_FRONTEND=false ./scripts/deploy.sh   # participant accounts without portal
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1

[[ -f .env ]] || { echo "❌ Missing .env -> cp .env.example .env and edit it"; exit 1; }
poetry install --no-interaction --quiet

# Read parameters with the SAME loader CDK uses (cdk.json defaults + .env), no shell sourcing
read -r REGION RESOURCE_PREFIX CUSTOMER_NAME < <(poetry run python - <<'PY'
import json, sys
sys.path.insert(0, "infrastructure")
from helpers.config import resolve_app_config
cfg = resolve_app_config(json.load(open("infrastructure/cdk.json"))["context"]["app_config"]["dev"])
print(cfg["aws_region"], cfg["resource_prefix"], cfg["customer_name"])
PY
)
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
echo "🚀 Deploying '${RESOURCE_PREFIX}' for ${CUSTOMER_NAME} to account ${ACCOUNT} (${REGION})"
if [[ "${DEPLOY_FRONTEND:-true}" == "true" ]]; then
  (cd frontend && npm ci --silent && npm run build --silent)
fi

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$REGION" >/dev/null 2>&1; then
  (cd infrastructure && npx cdk bootstrap "aws://${ACCOUNT}/${REGION}")
fi
(cd infrastructure && npx cdk deploy --all --require-approval never --outputs-file cdk-outputs.json)
echo "✅ Done. Outputs in infrastructure/cdk-outputs.json"
grep -o '"CloudFrontURL": "[^"]*"' infrastructure/cdk-outputs.json || true
