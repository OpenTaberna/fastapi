# Analytics

Admin-only commercial reporting, under `/v1/admin/analytics`.

Before this existed, the admin dashboard derived every money figure client-side
from the most recent 100 orders. That is fine for a demo and wrong for a shop:
the numbers stop being true the moment the hundred-and-first order is placed.
These endpoints compute the same figures in SQL over the whole order history.

## Endpoints

| Endpoint | Answers |
|---|---|
| `GET /summary` | What did we take, and how does that compare to last period? |
| `GET /timeseries` | How did that move day by day? |
| `GET /products` | What sold, what came back, what never sold at all? |
| `GET /funnel` | Where do orders stop? |

All four take optional `from` and `to` calendar dates, inclusive, defaulting to
the last 30 days.

## Definitions

These are choices, not facts, so they are written down rather than left implicit
in a query:

| Term | Definition |
|---|---|
| Gross revenue | Orders in `paid`, `ready_to_ship` or `shipped` |
| Refunded | Orders in `refunded` — **whole-order only** |
| Net revenue | Gross less refunded |
| Average order value | Gross divided by revenue-producing orders |
| Units | Line quantities on revenue-producing orders |

Never counted: `draft`, `pending_payment`, `cancelled`, and anything with
`deleted_at` set.

## Four things that are easy to get wrong

**Money is grouped by currency.** `orders.currency` permits more than one, and a
cross-currency total is not slightly wrong — it is meaningless. Every money
figure is therefore a list keyed by currency, which collapses to a single entry
for the usual single-currency shop.

**Order money and line money are queried separately.** Joining `orders` to
`order_items` and summing `total_amount` multiplies each order's value by its
line count. The join is only ever used for quantities and line revenue; order
totals come from their own statement and the two are merged in Python.

**Days are cut in the shop's timezone.** `SHOP_TIMEZONE` (default
`Europe/Berlin`) feeds `timezone(tz, created_at)`, Postgres' `AT TIME ZONE`.
Bucketing on raw UTC moves evening orders into the following day for any shop
east of Greenwich, which is the kind of error that looks like a data problem for
weeks.

**Checkout is read from `payments`, not from `orders.status`.** Status records
only where an order is *now*. A cancelled order is indistinguishable from one
that never reached checkout, and a shipped-then-refunded order no longer says it
shipped. A payment row is written when checkout starts and survives whatever
happens next.

## Known limits

Stated here because a reader will otherwise infer something stronger:

- **The funnel is an order funnel, not a visitor funnel.** It begins at order
  creation and cannot see shoppers who browsed and never started one. Visitor
  conversion needs session data the API does not collect. That is S2.
- **Partial refunds are not modelled.** `orders.status = refunded` is
  all-or-nothing, so refund figures will not reconcile against a partially
  refunded Stripe charge.
- **Return rate is an upper bound per SKU.** Returns are recorded per order, not
  per line, so a return on a two-line order counts against both SKUs.
- **Product revenue need not equal order revenue.** Product figures sum line
  values; an order total may carry shipping or adjustments belonging to no line.

## Performance

Aggregates are computed live rather than from a rollup table — always current,
no staleness, no extra moving parts. Three indexes support it:

```sql
ix_orders_created_at         (created_at)
ix_orders_status_created_at  (status, created_at)
ix_order_items_sku           (sku)
```

The schema is created with `Base.metadata.create_all`, which creates missing
*tables* but does not alter existing ones. A database that predates this change
therefore needs the indexes applied by hand:

```sql
CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders (created_at);
CREATE INDEX IF NOT EXISTS ix_orders_status_created_at ON orders (status, created_at);
CREATE INDEX IF NOT EXISTS ix_order_items_sku ON order_items (sku);
```

Without them the endpoints still return correct figures, just with a sequential
scan. A window longer than five years is refused outright, since live
aggregation has no rollup behind it to make an unbounded range cheap.

When order volume outgrows live aggregation, the next step is a nightly rollup
table written by the ARQ worker — deliberately not built yet, because it costs a
job, a table and staleness in exchange for speed nobody needs at this size.

## Testing

- `tests/test_analytics_unit.py` — period arithmetic, timezone conversion,
  gap filling, undefined-vs-infinite percentage change. No database.
- `tests/test_analytics_integration.py` — seeds a deterministic dataset inside
  March 2025, a window nothing else touches, and asserts exact figures. Covers
  currency isolation, soft-delete exclusion, the multi-line fan-out trap, the
  23:30-UTC timezone boundary, and the payments-based funnel.
