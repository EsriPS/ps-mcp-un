# Security Policy

## Supported versions

PS-MCP is in active 0.x development. Only the latest released minor version
receives security fixes.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Email the maintainers privately or use GitHub's "Report a vulnerability"
feature on the repository's Security tab. Include:

- A description of the vulnerability and its impact.
- Steps to reproduce, ideally with a minimal proof-of-concept.
- Affected versions / commit SHAs.
- Any suggested mitigations.

You should expect an acknowledgement within a few business days. We will
coordinate a fix and a coordinated disclosure timeline with you before
publishing details.

## Sensitive configuration

The server reads several secrets from environment variables:

- `ARCGIS_TOKEN` — ArcGIS Enterprise authentication token
- `OPENAI_KEY` — Azure OpenAI / OpenAI API key (used by the `arcgis` and
  `mongo` routers)
- `MONGO_DB_CONN`, `POSTGRES_DB_CONN` — database connection strings

**Never** commit `.env` files containing real values. Use `.env.sample` as a
template; the per-deployment files in `env-files/<deployment>/` should be
gitignored or stored in a secrets manager.

## SSL verification

The ArcGIS-facing routers/modules read `ARCGIS_VERIFY_SSL` and default to
`True`. Set `ARCGIS_VERIFY_SSL=false` only if connecting to a self-signed
Enterprise install, and **always use a properly signed certificate in
production.**

