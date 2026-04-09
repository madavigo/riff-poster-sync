#!/usr/bin/env bash
# Run this once to configure Vault auth for the CronJob.
# Requires: kubectl access to the cluster and Vault root/admin token.
set -euo pipefail

# Enable Kubernetes auth if not already enabled
kubectl exec -n vault vault-0 -- vault auth enable kubernetes 2>/dev/null || true

# Configure Kubernetes auth backend
kubectl exec -n vault vault-0 -- sh -c '
  vault write auth/kubernetes/config \
    kubernetes_host="https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT"
'

# Create a policy for reading the rifftrax-poster-sync secret
kubectl exec -n vault vault-0 -- vault policy write rifftrax-poster-sync - <<'POLICY'
path "secret/data/resilience-lab/rifftrax-poster-sync" {
  capabilities = ["read"]
}
POLICY

# Create a Kubernetes auth role bound to the service account
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/rifftrax-poster-sync \
  bound_service_account_names=default \
  bound_service_account_namespaces=media \
  policies=rifftrax-poster-sync \
  ttl=1h
