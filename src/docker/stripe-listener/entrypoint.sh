#!/bin/sh
set -eu

secret_file=/run/secrets/stripe_webhook_secret
output_fifo=/tmp/stripe-listener-output

if [ -z "${STRIPE_SECRET_KEY:-}" ]; then
  echo "STRIPE_SECRET_KEY must be set in .env" >&2
  exit 1
fi

# Do not let the API become healthy with a secret left by an older listener.
rm -f "$secret_file" "$output_fifo"
mkfifo "$output_fifo"

awk '
  {
    print
    fflush()
    if (match($0, /whsec_[[:alnum:]]+/)) {
      secret = substr($0, RSTART, RLENGTH)
      print secret > "/run/secrets/stripe_webhook_secret.tmp"
      close("/run/secrets/stripe_webhook_secret.tmp")
      system("mv /run/secrets/stripe_webhook_secret.tmp /run/secrets/stripe_webhook_secret")
    }
  }
' < "$output_fifo" &
log_pid=$!

/bin/stripe listen \
  --api-key "$STRIPE_SECRET_KEY" \
  --events payment_intent.succeeded,payment_intent.payment_failed \
  --forward-to http://opentaberna-api:8000/v1/webhooks/stripe \
  > "$output_fifo" 2>&1 &
stripe_pid=$!

shutdown() {
  kill -TERM "$stripe_pid" 2>/dev/null || true
  wait "$stripe_pid" 2>/dev/null || true
  kill -TERM "$log_pid" 2>/dev/null || true
}

trap shutdown INT TERM

set +e
wait "$stripe_pid"
status=$?
set -e

kill -TERM "$log_pid" 2>/dev/null || true
wait "$log_pid" 2>/dev/null || true
exit "$status"
