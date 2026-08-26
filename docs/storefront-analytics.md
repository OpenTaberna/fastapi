# Storefront Analytics

Anonymous shopper telemetry, so the funnel can start before an order exists.

`GET /v1/admin/analytics/funnel` begins at order creation. It answers "how many
orders were paid" but not "how many people looked and left" — and the second
question is usually the more useful one. Browsing, product views and abandoned
carts leave no trace in the order tables, because nothing happened there.

## How it fits together

```
storefront  ──POST /v1/analytics/events──▶  storefront_events
   (public, rate limited, opt-in)                  │
                                                   ▼
                              GET /v1/admin/analytics/storefront
                                                   │
                                     joins the paid step from `orders`
```

## Privacy

The table holds no column that could identify a person: no customer id, no
email, no IP address, no user agent. A shopper is represented only by
`session_id`, an opaque value their own browser generates and discards when the
tab closes.

This is not a policy someone has to remember. It is enforced in three places:

**The schema.** There is nowhere to put an IP address.
`test_the_table_has_no_column_that_could_identify_a_person` fails if a column
named for an address, an identity or a device ever appears.

**The request schema.** `extra="forbid"`, so a client sending `email` or
`ip_address` gets a `422` rather than having the field quietly dropped. Silently
discarding it would let a frontend believe it was collecting something it was
not — which is worse than refusing, because nobody finds out.

**The path validator.** Query strings are stripped before storage. A query
string is where personal data arrives by accident — an email in a share link, a
token in a redirect — and removing it at the boundary means it cannot be stored
even if a client sends it.

Because nothing here identifies anyone and nothing is stored in the browser
beyond a per-tab session id, this needs no consent banner in the EU. That is not
a happy accident; it is why the design is shaped this way. A banner costs
40-60% of sessions to opt-outs, which would make the funnel it feeds mostly
fiction.

## Off unless the operator turns it on

`STOREFRONT_ANALYTICS_ENABLED` defaults to `false` and the ingest endpoint
returns `404` while it is. Cloning OpenTaberna must not silently start
collecting anything, even something that identifies nobody.

`404` rather than `403` so a deployment that has not opted in does not advertise
a capability it is not offering.

The admin endpoint still answers when collection is off — it reports
`enabled: false` with zeroes, which distinguishes "nobody visited" from "we are
not counting". Those look identical otherwise, and an operator staring at an
empty funnel deserves to know which they are looking at.

## The ingest endpoint is public

Anyone who can load the shop can post to it. That shapes everything:

| Guard | Why |
|---|---|
| Rate limited to 120/minute per address | An open write endpoint otherwise fills a table |
| Batch capped at 50 events | One request cannot be a bulk insert |
| Closed event vocabulary | A client cannot write arbitrary strings into a table an admin reads |
| `extra="forbid"` | Unexpected fields are refused, not ignored |
| Every field length-bounded | No unbounded text reaches storage |
| Returns `202` | The browser must not wait on it, and must not retry into a queue during an incident |

The worst an abusive client can achieve is noise in a report. It cannot store
anything about anyone, and it cannot affect an order.

## Timestamps are not trusted

Events carry the browser's `occurred_at`, and browser clocks are wrong often
enough that discarding all skew would lose real data. Events more than 24 hours
either side of server time are dropped and counted in `rejected`.

The window exists so a client cannot write into a period an administrator has
already reported on. `created_at` records when the API stored the event and is
trustworthy; `occurred_at` is what the browser claimed.

## The last step is not taken on trust

The funnel's `paid` step is **not** read from the events table. A browser
reporting `checkout_started` means a button was pressed; whether money arrived
is knowable only from `orders`.

So `checkout_started` carries an `order_id`, and the API counts how many of
those orders actually reached a revenue-producing status. A client claiming a
checkout it never paid for inflates one step and cannot touch the next.

`order_id` is deliberately **not** a foreign key. The event records what a
browser reported, and must survive the order being deleted rather than vanishing
with it and silently improving the conversion rate.

## What the numbers mean

Sessions are counted distinctly. Ten product views from one shopper is one
person considering a purchase, not ten.

| Step | Source |
|---|---|
| Visited the shop | Any event in the window |
| Viewed a product | A `product_view` |
| Added to cart | An `add_to_cart` |
| Started checkout | A `checkout_started` |
| Paid | `orders`, joined on the reported `order_id` |

**The pre-order steps are a floor, not a count.** Blocked scripts, a tab closed
before the batch flushed and disabled JavaScript all lose events. The paid step
is exact. They are labelled differently in the UI for that reason rather than
presented as one continuous measurement — a funnel whose first step undercounts
and whose last step does not will overstate conversion, and a reader should know
which end is soft.

`add_to_cart_rate` per SKU is the figure worth watching: a product viewed often
and added rarely means the listing draws people in and something — price, stock,
photography — turns them away. Sales figures cannot show this, because they only
ever contain what did sell.

## Testing

- `tests/test_storefront_analytics_unit.py` — the schema as a boundary: query
  string stripping, closed vocabulary, forbidden extras, batch caps.
- `tests/test_storefront_analytics_integration.py` — ingest without auth, the
  PII-column assertion, clock-skew rejection, session-distinct counting, and
  that a fabricated `order_id` cannot inflate the paid step.
