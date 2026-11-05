#!/usr/bin/env bash
set -euo pipefail

# Port-forward Grafana
nohup kubectl --context twolevel-dev -n monitoring port-forward --address 127.0.0.1 "service/monitoring-grafana" "3000:80" > /tmp/pf-grafana.log 2>&1 &

# Port-forward Prometheus
nohup kubectl --context twolevel-dev -n monitoring port-forward --address 127.0.0.1 service/monitoring-kube-prometheus-prometheus 9090:9090 > /tmp/pf-prom.log 2>&1 &
