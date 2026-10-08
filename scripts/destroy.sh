#!/usr/bin/env bash
# Remove notebook-created AI resources and then the CDK stacks of the current account.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1
.venv/bin/python workshop/99_cleanup/99_cleanup.py || true
(cd infrastructure && npx cdk destroy --all --force)
