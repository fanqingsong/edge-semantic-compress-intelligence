#!/bin/sh
set -eu

runtime_dir=/mosquitto/runtime
certificate_dir="${runtime_dir}/certs"
mkdir -p "${certificate_dir}"

for certificate in ca.crt broker.crt broker.key healthcheck.crt healthcheck.key; do
  cp "/run/mqtt-certs/${certificate}" "${certificate_dir}/${certificate}"
done
cp /mosquitto/config/aclfile "${runtime_dir}/aclfile"

chown -R mosquitto:mosquitto "${runtime_dir}"
chmod 750 "${runtime_dir}" "${certificate_dir}"
chmod 640 "${certificate_dir}"/*.key "${certificate_dir}"/*.crt
chmod 600 "${runtime_dir}/aclfile"

exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf