# Saxo OpenAPI adapter

`cheshire_cat.saxo.SaxoOpenAPI` is a small adapter for account, balance,
position, open-order, and instrument-price reads. It defaults to Saxo's SIM
environment and does not place orders. `preview_order` only builds a payload;
`place_order` requires both `SAXO_ALLOW_ORDERS=1` (or
`SaxoConfig(allow_orders=True)`) and `confirm="PLACE_ORDER"`.

## Setup

1. Create a free simulation account and a simulation application in Saxo's
   developer portal.
2. For a quick test, obtain a 24-hour access token and set
   `SAXO_ACCESS_TOKEN`. For a persistent integration, configure OAuth and store
   the access/refresh-token flow outside this repository.
3. Set `SAXO_ENVIRONMENT=sim` explicitly while testing. Use `live` only after
   reviewing account permissions, rate limits, and order controls.
4. Construct `SaxoOpenAPI(SaxoConfig.from_environment())` and call read-only
   methods first. Account keys and client keys come from the account endpoints;
   do not hard-code them.

The SIM gateway is `https://gateway.saxobank.com/sim/openapi`; the live gateway
is `https://gateway.saxobank.com/openapi`. Endpoint details and permissions
can change, so consult Saxo's official [getting started guide](https://openapi.help.saxo/hc/en-us/articles/5231611647517-How-do-I-get-started-with-OpenAPI),
[live authentication guide](https://openapi.help.saxo/hc/en-us/articles/4416636625041-How-can-I-get-an-access-token-for-the-live-environment),
and [portfolio reference](https://www.developer.saxo/openapi/learn/portfolio).

This adapter is not connected to the research dashboard automatically. A
research result is never an order instruction, and no live credentials are
required for price/fundamental research.
