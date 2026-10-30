#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/08-port-forward.sh [--port PORT] [--namespace NAMESPACE] [--service SERVICE]

Forward a local port to Grafana. Defaults: port 3000, namespace monitoring,
service monitoring-grafana. Press Ctrl+C to stop.
EOF
}

port=3000
namespace=monitoring
service=monitoring-grafana

while (( $# )); do
  case "$1" in
    --port|--namespace|--service)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
        printf 'Missing value for %s\n' "$1" >&2
        exit 2
      fi
      case "$1" in
        --port) port=$2 ;;
        --namespace) namespace=$2 ;;
        --service) service=$2 ;;
      esac
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
  printf 'Port must be an integer between 1 and 65535.\n' >&2
  exit 2
fi

if ! command -v kubectl >/dev/null 2>&1; then
  printf 'kubectl was not found. Install it and configure access to the EKS cluster.\n' >&2
  exit 1
fi

printf 'Forwarding http://localhost:%s to service/%s in namespace %s.\n' "$port" "$service" "$namespace"
printf 'Wait for the kubectl forwarding message, then open the URL. Press Ctrl+C to stop.\n'
exec kubectl -n "$namespace" port-forward --address 127.0.0.1 "service/$service" "$port:80"
