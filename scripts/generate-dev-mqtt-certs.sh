#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cert_dir="${1:-${repo_root}/deploy/mosquitto/certs}"
mkdir -p "${cert_dir}"
chmod 700 "${cert_dir}"
umask 077

openssl req -x509 -newkey rsa:4096 -sha256 -days 365 \
  -nodes -keyout "${cert_dir}/ca.key" \
  -out "${cert_dir}/ca.crt" \
  -subj "/CN=edge-semantic-compress-dev-ca"

issue_certificate() {
  local identity="$1"
  local extended_usage="$2"
  local subject_alt_name="${3:-}"
  local name="${cert_dir}/${identity}"
  local extension_file="${name}.ext"

  openssl req -new -newkey rsa:2048 -sha256 -nodes \
    -keyout "${name}.key" \
    -out "${name}.csr" \
    -subj "/CN=${identity}"

  {
    printf '[v3_req]\n'
    printf 'basicConstraints=CA:FALSE\n'
    printf 'keyUsage=digitalSignature,keyEncipherment\n'
    printf 'extendedKeyUsage=%s\n' "${extended_usage}"
    if [[ -n "${subject_alt_name}" ]]; then
      printf 'subjectAltName=%s\n' "${subject_alt_name}"
    fi
  } >"${extension_file}"

  openssl x509 -req -in "${name}.csr" \
    -CA "${cert_dir}/ca.crt" -CAkey "${cert_dir}/ca.key" \
    -CAcreateserial -out "${name}.crt" -days 365 -sha256 \
    -extfile "${extension_file}" -extensions v3_req
  rm -f "${name}.csr" "${extension_file}"
}

issue_certificate "broker" "serverAuth" "DNS:emqx,DNS:localhost,IP:127.0.0.1"
issue_certificate "edge-agent" "clientAuth"
issue_certificate "cloud-agent" "clientAuth"
issue_certificate "mqtt-kafka-bridge" "clientAuth"
issue_certificate "healthcheck" "clientAuth"

openssl verify -CAfile "${cert_dir}/ca.crt" \
  "${cert_dir}/broker.crt" \
  "${cert_dir}/edge-agent.crt" \
  "${cert_dir}/cloud-agent.crt" \
  "${cert_dir}/mqtt-kafka-bridge.crt" \
  "${cert_dir}/healthcheck.crt"
chmod 600 "${cert_dir}"/*.key
chmod 644 "${cert_dir}"/*.crt
printf 'Generated development MQTT certificates in %s\n' "${cert_dir}"