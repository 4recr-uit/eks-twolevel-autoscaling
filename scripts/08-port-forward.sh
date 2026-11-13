#!/usr/bin/env bash
set -euo pipefail

# Port-forward Grafana
nohup kubectl --context twolevel-dev -n monitoring port-forward --address 127.0.0.1 "service/monitoring-grafana" "3000:80" > /tmp/pf-grafana.log 2>&1 &

# Port-forward Prometheus
nohup kubectl --context twolevel-dev -n monitoring port-forward --address 127.0.0.1 service/monitoring-kube-prometheus-prometheus 9090:9090 > /tmp/pf-prom.log 2>&1 &

# Port-forward orders-queue
nohup kubectl --context twolevel-dev -n retailstore port-forward --address 127.0.0.1 service/orders 8082:80 > /tmp/pf-orders.log 2>&1 &

echo "Running in background: 
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Orders-queue: http://localhost:8082"