FROM stripe/stripe-cli:v1.42.0

COPY --chmod=755 src/docker/stripe-listener/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
