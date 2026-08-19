# Mongo vector search module

The `mongo` router provides MongoDB Atlas vector search plus a few schema-inspection helpers that make it easier to discover collections, inspect indexes, and build useful pre-filters.

## Route name

`mongo`

## Tools

1. `mongo_vector_search` — run a vector search against a collection using a required vector search index and an optional MongoDB filter.
2. `mongo_list_collections` — list collection names in the configured database.
3. `mongo_get_collection_info` — return collection options/metadata.
4. `mongo_collection_find_one` — fetch a sample document using a filter.
5. `mongo_collection_get_indexes` — list available vector search indexes and filterable indexed fields.

## Resource

- `resource://mongo_service/mongo_filter_info`

## Prompt

- `mongo_vector_search_prompt`

## Configuration

- `MONGO_DB_CONN`
- `MONGO_DB_NAME`
- `CONTEXT_COUNT`
- `CANDIDATES_MULTIPLIER`
- `OPENAI_KEY`
- `MONGO_OPENAI_BASE_URL`
- `MONGO_OPENAI_API_VERSION`
- `EMBEDDING_DEPLOYMENT`

## Notes

- `mongo_vector_search` currently requires all of: `collection_name`, `query`, `vector_search_index`, and `search_filter`.
- Pass `{}` for `search_filter` when no filter helps.
- The prompt encourages discovering valid `vector_search_index` values through `mongo_collection_get_indexes` before searching.

## Related docs

- [`mongo_pre_filter.md`](mongo_pre_filter.md)
