# Authorization

User management runs on Keycloak. The realm is managed **in this repository**
(`keycloak/opentaberna-realm.json`) and imported on container start, so the
whole setup is reproducible from a clean checkout.

## Two kinds of user

| Role | How it is granted | What it allows |
|---|---|---|
| `customer` | Automatically, to every account | Nothing special. It is the default role. |
| `admin` | Only by another admin | The back-office endpoints under `/v1/admin/**`. |

`customer` is attached to `default-roles-opentaberna`, so anyone who registers
receives it without an administrator doing anything.

`admin` is a composite that also carries the `realm-management` roles
`manage-users`, `view-users`, `query-users` and `view-realm`. That is what makes
"admins are created by admins" true rather than aspirational: an existing admin
holds exactly the permissions needed to read the `admin` role and assign it to
someone else, and a customer holds none of them. A customer attempting either
gets `403` from Keycloak itself — the API is not involved.

`view-realm` is easy to miss. Without it an admin can call the user endpoints
but cannot read the role definition they are trying to grant, so promotion
fails with a confusing 403.

## Clients

| Client | Type | Purpose |
|---|---|---|
| `opentaberna-api` | confidential | The resource server. Validates tokens; mints none. Its client id is the audience the API expects. |
| `opentaberna-admin-ui` | public, PKCE | Back-office frontend. **The only client whose tokens are accepted on admin endpoints.** |
| `opentaberna-store-ui` | public, PKCE | Storefront. Never accepted on admin endpoints. |

Both frontends carry an audience mapper adding `opentaberna-api` to the token,
because a public client otherwise receives a token scoped only to `account`,
leaving the API nothing meaningful to validate.

## What the API enforces

**Admin endpoints** (`/v1/admin/**`) require all three:

1. a token whose signature, issuer, audience and expiry check out,
2. the `admin` realm role,
3. an `azp` in `keycloak_admin_client_ids`.

The third is the interesting one. Roles alone are not enough: an administrator
browsing the shop still carries the `admin` role in their storefront token, so
accepting it would let any script on the shop page drive the back office.

**Everything else** needs no role. Customer-scoped endpoints identify the caller
from the token when one is presented — a verified `sub` always beats the
`X-Keycloak-User-ID` header, so a caller cannot read another customer's profile
by supplying an id alongside their own valid token. The catalogue, health
endpoints and Stripe webhook stay open to everyone.

## Where profile data lives

Keycloak owns **e-mail** and the optional **phone number**; the customer edits
them in their account and the API mirrors them onto the local profile whenever
it sees a token. Shipping **addresses** stay in the API, because orders
reference an address row by foreign key and carrier labels are printed from it.
Nothing is stored in both places, so there is nothing to drift.

Phone is declared as an optional attribute on the realm's user profile and
mapped into the token as `phone_number`.

## Development without Keycloak

`X-Admin-Key` (any non-empty value) and `X-Keycloak-User-ID` stand in for a
token so local work and the test suite do not need a running Keycloak. A bearer
token always wins over them.

A `Settings` validator forces `auth_allow_dev_headers` to `false` when
`ENVIRONMENT=production`. Those headers let any caller claim any identity, so
leaving them live in production would make every admin endpoint publicly
writable.

## Changing the realm

The realm is imported with `IGNORE_EXISTING`, and Keycloak's data now lives in
the `keycloak_data` volume so registered users survive a container restart. The
consequence is that **editing the realm file does not update a realm that has
already been imported**. To pick up a change in development:

```bash
docker compose -f docker-compose.dev.yml rm -sf opentaberna-keycloak
docker volume rm fastapi_opentaberna_keycloak_data
docker compose -f docker-compose.dev.yml up -d opentaberna-keycloak
```

That regenerates every user's `sub`. Profiles created against the old ids are
then orphaned, and because e-mail is unique the API will refuse to create a
second profile for the same address — reported as a clear conflict rather than
a constraint crash. Clear the affected rows from `customers` when this happens
locally.

## Seeded users

Both exist for development only.

| Username | Password | Roles |
|---|---|---|
| `testuser` | `testpassword` | `customer` |
| `adminuser` | `adminpassword` | `customer`, `admin` |

## Getting a token by hand

```bash
curl -s -X POST \
  http://localhost:8080/realms/opentaberna/protocol/openid-connect/token \
  -d client_id=opentaberna-admin-ui \
  -d grant_type=password \
  -d username=adminuser \
  -d password=adminpassword | jq -r .access_token
```

Swap `opentaberna-admin-ui` for `opentaberna-store-ui` to see an admin refused
on an admin endpoint — the check that keeps the back office off the shop.
