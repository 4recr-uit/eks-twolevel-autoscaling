#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo 'This script accepts no arguments.' >&2; exit 2; }
cd "$(dirname "$0")/.."
kubectl --context twolevel-dev -n monitoring create configmap autoscaling-dashboard \
  --from-file=observability/dashboards/autoscaling-overview.json --dry-run=client -o yaml | \
  kubectl --context twolevel-dev apply -f -
kubectl --context twolevel-dev -n monitoring label configmap autoscaling-dashboard grafana_dashboard=1 --overwrite
echo 'Dashboard updated. Refresh Grafana; configure CloudWatch separately as documented in docs/OBSERVABILITY.md.'
