# Observability

OpenTelemetry traces and metrics from the API and the worker, exported over OTLP.

Before this the API had structured logs and correlation IDs and nothing else.
"The shop feels slow" could not be answered with anything but a guess, and a
regression in one endpoint stayed invisible until somebody reported it.

## OTLP is the seam

No application module imports a vendor SDK. Everything speaks OTLP to a
collector, and the collector decides where telemetry goes. Using Datadog or
Grafana Cloud instead of the bundled stack is a change to
`OTEL_EXPORTER_OTLP_ENDPOINT` and the collector's config — not a change to any
service.

```
API ────┐
        ├──▶ OTel Collector ──▶ Prometheus ──▶ Grafana
Worker ─┘         (:4318)         (:9090)      (:3001)
```

## Off by default

`OTEL_ENABLED` defaults to `false`, and while it is off `setup()` returns before
creating an exporter — so a deployment that has not opted in opens no
connection and sends nothing anywhere.

## It must never take the application down

Every step of the wiring is wrapped. A collector that is absent, unreachable or
misconfigured produces a warning and a running API, not a failed start.
Observability that can cause the outage it exists to diagnose is a bad trade,
and the tests pin this: an exporter that raises on construction still leaves
`setup()` returning `False` rather than propagating.

## What is instrumented

| Source | Gives you |
|---|---|
| FastAPI | Request rate, latency histogram, status codes, in-flight requests |
| SQLAlchemy | Query spans and connection pool usage |
| Redis | Command spans |
| httpx | Outbound calls — Stripe, DHL, Keycloak |

Health endpoints are excluded. A liveness probe every few seconds would
otherwise dominate the trace volume and the request-rate metric, burying real
traffic under a heartbeat.

## Business gauges

`Deployment.md` names the queue states worth alerting on. They used to be
queries an operator had to remember to run, which means nobody ran them and the
first sign of a stalled pipeline was a customer asking where their parcel was.

| Metric | Non-zero means |
|---|---|
| `opentaberna.outbox.pending` | Rising: the worker is not running |
| `opentaberna.outbox.failed` | Events never reached the queue — Redis or the poller |
| `opentaberna.outbox.dead` | Jobs ran and gave up — usually the carrier API |
| `opentaberna.webhooks.unprocessed` | Payments arriving, not handled. **Page on this.** |
| `opentaberna.orders.awaiting_shipment` | The work queue, not necessarily a fault |

**These are collected by the worker, on a 30-second cron.** The first version
used observable gauges whose callbacks run on the metrics SDK's own thread — and
the only database engine here is asynchronous, so driving it from outside the
event loop failed. The gauges registered cleanly and then silently produced
nothing, which is the worst kind of monitoring bug. The worker already runs a
scheduler and holds an async session, and is the process that most needs to be
alive for these numbers to matter.

## Traces and logs are joined

Every log record carries `trace_id` alongside `correlation_id`. Without it the
two systems describe the same request and cannot be put side by side — you would
find a slow span in Grafana and have no way to reach the log lines explaining it.
The field is empty when tracing is off, so it is always present and a formatter
never raises.

## Running it

```bash
# in .env
OTEL_ENABLED=true

docker compose -f docker-compose.dev.yml up -d
```

| Service | URL |
|---|---|
| Grafana | http://localhost:3001 — anonymous, dashboard provisioned |
| Prometheus | http://localhost:9090 |
| Collector metrics | http://localhost:8889/metrics |

Grafana is anonymous **in the development compose file only**. The dashboard is
read-only and holds no secrets, and requiring a login to look at a latency graph
on your own laptop helps nobody. Do not copy that setting to production.

## The dashboard

`OpenTaberna — Health`, provisioned from
`src/docker/observability/grafana/dashboards/`. Three rows: the queue gauges
above, request rate/error rate/latency percentiles, and dependency health.

Two details worth keeping if you edit it:

**The error-rate panel ends in `or vector(0)`.** Without it a healthy shop shows
"No data", which is indistinguishable from a broken scrape — and is exactly the
wrong thing to be uncertain about during an incident.

**Latency panels use p95 and p99, never an average.** An average hides the slow
tail that customers actually notice.

The FastAPI instrumentation labels the path as `http_target`, not `http_route`.
Grouping by `http_route` silently collapses every route into one unnamed series,
which looks like a working panel. That mistake is already made and fixed here.

## Production

- Set `OTEL_EXPORTER_OTLP_ENDPOINT` to your collector.
- Set `OTEL_SERVICE_NAME` per process — the worker overrides it in compose.
- Do not expose Grafana anonymously.
- Alert on `webhooks_unprocessed` and `outbox_failed` first: both mean money has
  moved and the system has not noticed.

## Testing

- `tests/test_telemetry_unit.py` — off unless opted in, idempotent setup, and
  every failure mode degrading to "no telemetry" rather than "no API".
- `tests/test_telemetry_integration.py` — asserts against the collector's
  output and Prometheus, not against the fact that setup was called. That
  distinction caught the real bug: instrumenting the app before configuring
  telemetry logged a clean start and produced no HTTP metrics at all.
