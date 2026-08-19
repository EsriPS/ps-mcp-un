# PostgreSQL vector search module

The `postgres` router provides pgvector-backed search over a configured PostgreSQL table. It includes the main search tool plus helpers for sampling a single record and inspecting the table schema used for filtering.

## Route name

`postgres`

## Tools

1. `postgres_vector_search` — run a similarity search with an optional structured pre-filter.
2. `postgres_vector_find_one` — fetch a single representative result to inspect record shape and refine filters.
3. `postgres_get_table_schema` — return the configured vector table schema and column metadata.

## Resource

- `resource://postgres_service/postgres_filter_info`

## Prompt

- `postgres_vector_search_prompt`

## Configuration

- `POSTGRES_DB_CONN`
- `POSTGRES_VECTOR_STORE_TABLE`
- `POSTGRES_CONTEXT_COUNT`
- `POSTGRES_VECTOR_STORE_ID_COLUMN`
- `POSTGRES_VECTOR_STORE_EMBEDDING_COLUMN`
- `POSTGRES_VECTOR_STORE_METADATA_COLUMNS`
- `POSTGRES_VECTOR_SEARCH_SCORE_THRESHOLD`
- `POSTGRES_VECTOR_SEARCH_MAX_ATTEMPTS`
- `OPENAI_KEY`
- `POSTGRES_OPENAI_BASE_URL`
- `POSTGRES_OPENAI_API_VERSION`
- `POSTGRES_EMBEDDING_DEPLOYMENT`

## Notes

- `POSTGRES_CONTEXT_COUNT` is read at import time in the current implementation, so it needs to be set when the router is enabled.
- Empty semantic queries are supported in `postgres_vector_search`; the code uses a placeholder query and skips score-threshold filtering when `query` is blank.
- Filter date strings are converted to `datetime` values before search.

## Related docs

- [`postres_filter.md`](postres_filter.md)
