# RapidAPI Distribution Notes

## A. Overview

Naruto Mythos TCG Developer API

This project provides a developer-facing, read-only catalogue API for Naruto Mythos TCG data. It is intentionally presented as a public developer API, not as an official Naruto API, and it does not claim affiliation or endorsement from Naruto rights holders or the original card-game publisher.

## B. Architecture

```text
Consumer
    ↓
RapidAPI
    ↓
X-RapidAPI-Proxy-Secret
    ↓
Railway / FastAPI
    ↓
PostgreSQL
```

The canonical app remains a FastAPI application. The origin service exposes a public API on Railway. When a live RapidAPI gateway is configured, the gateway handles consumer authentication and forwards requests to the origin with the origin-protection header set.

## C. Authentication

### Consumer-facing headers

The consumer-facing authentication model is:

- `X-RapidAPI-Key`
- `X-RapidAPI-Host`

These are validated by RapidAPI itself before a request reaches the origin. The origin API does not validate them.

### Origin-facing protection

Origin protection is optional and uses:

- `X-RapidAPI-Proxy-Secret`

This value is only relevant between RapidAPI and the origin service. It is not intended to be used by ordinary API clients.

## D. Origin protection

The origin service includes optional protection for `/v1` traffic when the environment variable `RAPIDAPI_PROXY_SECRET` is configured. When set:

- `GET /v1/...` requires the exact `X-RapidAPI-Proxy-Secret` header
- wrong or missing values return a standardized `403` response
- `/health` and `/ready` remain public
- docs endpoints remain public
- direct origin access without the header fails with `403`

When `RAPIDAPI_PROXY_SECRET` is unset, behavior is unchanged and the public API remains accessible directly from the origin.

## E. OpenAPI

Canonical application OpenAPI:

- OpenAPI 3.1.0
- generated from FastAPI directly
- exposed at `/openapi.json`

RapidAPI distribution OpenAPI:

- generated compatibility export
- OpenAPI 3.0.2
- derived from the canonical FastAPI schema
- generated deterministically using the repository export command

Regenerate the RapidAPI document with:

```bash
python -m scripts.export_rapidapi_openapi
```

The generated artifact is intentionally produced from the canonical app and not maintained by hand.

## F. Endpoints

The current developer API includes only the following existing routes:

- `GET /health`
- `GET /ready`
- `GET /v1/sets`
- `GET /v1/sets/{public_id}`
- `GET /v1/sets/{public_id}/cards`
- `GET /v1/cards`
- `GET /v1/cards/random`
- `GET /v1/cards/{public_id}`
- `GET /v1/rarities`
- `GET /v1/keywords`
- `GET /v1/keywords/{slug}/cards`
- `GET /v1/search`

No public write endpoints are exposed, and no importer or admin routes are part of the public API surface.

## G. Pagination, filter, and search

The public API behavior is intentionally read-only and follows the actual app contract:

- pagination is supported via `page` and `limit`
- invalid pagination values return the shared `400` error shape
- empty results still return `200` with an empty `data` array and pagination metadata
- filtering and sorting are request-driven and documented in the canonical OpenAPI
- search is available via `/v1/search`

## H. Errors

The standardized public error shape is:

```json
{
  "error": {
    "code": "SET_NOT_FOUND",
    "message": "Set not found."
  }
}
```

Current real error codes include:

- `CARD_NOT_FOUND`
- `SET_NOT_FOUND`
- `KEYWORD_NOT_FOUND`
- `INVALID_FILTER`
- `INVALID_PAGINATION`
- `INVALID_SORT`
- `FORBIDDEN`
- `INTERNAL_ERROR`

No stack traces, credentials, or SQL text are exposed in public responses.

## I. Rate limiting

Rate limiting and quota management belong to the RapidAPI gateway. The origin API does not claim to manage a current plan-level quota model. The recommended model is to let RapidAPI enforce quotas and use the origin as a private provider behind the gateway.

## J. Versioning

Current versioning in the app is:

- route prefix: `/v1`
- API version metadata: `1.0.0`

This is the stable, public contract intended for external consumer usage.

## K. IP and licensing

This project does not automatically imply affiliation, endorsement, sponsorship, or official status from Naruto rights holders, publishers, or related parties.

- trademarks and artwork remain the property of their respective rights holders
- copyrighted images, artwork, logos, and protected text require appropriate authorization before redistribution
- this is not legal advice

## L. Manual RapidAPI setup

The following steps remain manual after code-ready approval:

1. Sign into RapidAPI.
2. Create or configure the provider API.
3. Keep the listing private while the origin and runtime are validated.
4. Import the generated OpenAPI 3.0.2 document.
5. Configure the origin URL to `https://naruto-mythos-api-production.up.railway.app`.
6. Configure and test the Rapid Runtime.
7. Obtain the provider-side `X-RapidAPI-Proxy-Secret`.
8. Add it to Railway as `RAPIDAPI_PROXY_SECRET`.
9. Redeploy the service.
10. Verify direct `/v1` access without the proxy secret returns `403`.
11. Verify the RapidAPI proxied `/v1` request succeeds.
12. Configure plans.
13. Configure quotas and rate limits.
14. Test representative endpoints.
15. Review analytics.
16. Only then consider publishing the listing.

This is a manual provider-side step and is distinct from code completion.

## M. Initial plan recommendations

These are recommendations only and are not current configured limits:

- Free / development: conservative usage, low request caps, internal testing only
- Hobby / basic: moderate quotas, a small but stable consumer tier
- Production / pro: higher quota, stronger monitoring, private/limited listing until traffic stabilizes

No price or quota values are implied by the repository itself.
