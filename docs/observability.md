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

---

# Frontend Errors

Uncaught errors from the storefront and the admin UI.

Traces and metrics see nothing that happens in a browser. A component that
throws leaves the server returning 200 with healthy metrics while the shop is
broken for a real customer — and for a shop, by the time someone reports it the
sale is gone.

```
POST /v1/telemetry/errors        report (public, rate limited, opt-in)
GET  /v1/admin/telemetry/errors  read, grouped (admin)
```

## Public, and treated as such

Storefront visitors are not signed in, and an error that happens before login is
exactly the one worth catching — so the report endpoint takes no token. It is
therefore hostile-input territory:

| Guard | Why |
|---|---|
| 30 requests/minute per address | A component throwing in a render loop reports as fast as the browser can loop |
| 10 errors per batch | One request cannot be a bulk insert |
| Closed `app` vocabulary | The field cannot become free text |
| `extra="forbid"` | Unknown fields are refused, not ignored |
| Stack truncated at 4000 chars | Unbounded input, and the top frames are where the fault is |
| Off unless `FRONTEND_ERRORS_ENABLED` | Returns 404 while off |

## The user agent is reduced, never stored

A raw user-agent string is a fingerprint. But "which browser?" is genuinely
diagnostic — a large share of frontend bugs are one engine behaving differently
— so discarding it entirely makes the reports much weaker.

The compromise: reduce it at the boundary to a family and major version, and
store only that. `Safari 18` reproduces a bug; it does not recognise anyone.

The reduction is also a filter. Whatever a client sends, the output is a known
family name and an integer — never a fragment of the input:

```
"Mozilla/5.0 Chrome/140 user=alice@example.com token=abc123"  →  "Chrome 140"
```

There is no column for an IP address, an email or a customer id, and a test
fails if one appears.

## Errors are grouped

One bug produces thousands of identical rows, so the read endpoint groups by
application, error class and message, ordered by frequency.

Deliberately **not** grouped by stack: the same fault reached from two routes
produces two different stacks and is one bug. `affected_paths` shows the spread
instead, and one representative stack is returned for debugging.

## What this cannot tell you

It reports only what browsers managed to send. An error that breaks a page badly
enough to stop the reporter is precisely the one that will not appear — so a
quiet report is weaker evidence than a noisy one. Read silence as "no news",
never as "no errors".

## Testing

- `tests/test_frontend_errors_unit.py` — the user-agent reduction, including
  Edge not being reported as Chrome, and that nothing from the input string
  survives it.
- `tests/test_frontend_errors_integration.py` — reporting without auth, the
  PII-column assertion, the raw agent never reaching storage, query-string
  stripping, stale timestamps, and grouping across routes.
