"""
PostgreSQL Vector Search Service.

This module provides tools for interacting with PostgreSQL for vector search operations.
"""

# ============================================================================
# CONFIGURATION
# ============================================================================

import json
import logging
import os
import time
from datetime import datetime

from fastmcp import FastMCP
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

# Define any constants needed for the service
DB_CONN = os.getenv("POSTGRES_DB_CONN")
VECTOR_STORE_TABLE = os.getenv("POSTGRES_VECTOR_STORE_TABLE")
CONTEXT_COUNT = int(os.getenv("POSTGRES_CONTEXT_COUNT", "20"))
VECTOR_STORE_ID_COLUMN = os.getenv("POSTGRES_VECTOR_STORE_ID_COLUMN", "image_id")
VECTOR_STORE_EMBEDDING_COLUMN = os.getenv("POSTGRES_VECTOR_STORE_EMBEDDING_COLUMN", "embedding")
VECTOR_STORE_METADATA_COLUMNS = os.getenv(
    "POSTGRES_VECTOR_STORE_METADATA_COLUMNS",
    "site_id,group_name,image_date,extent_xmin,extent_ymin,extent_xmax,extent_ymax",
).split(",")
# Vector Search Configuration
VECTOR_SEARCH_SCORE_THRESHOLD = float(os.getenv("POSTGRES_VECTOR_SEARCH_SCORE_THRESHOLD", "0.4"))
VECTOR_SEARCH_MAX_ATTEMPTS = int(os.getenv("POSTGRES_VECTOR_SEARCH_MAX_ATTEMPTS", "5"))

# Multi-table catalog configuration
# POSTGRES_TABLES_CONFIG takes priority over single-table env vars
POSTGRES_TABLES_CONFIG_JSON = os.getenv("POSTGRES_TABLES_CONFIG")


def _load_tables_catalog() -> list[dict]:
    """
    Load the table catalog from environment variables.
    If POSTGRES_TABLES_CONFIG is set, parse it as a JSON array of table configs.
    Otherwise fall back to the single-table env vars for backward compatibility.

    Each table entry supports the following keys:
        name (str): Table name in the database (required).
        description (str): Human-readable description of the table.
        id_column (str): Name of the id column (default: POSTGRES_VECTOR_STORE_ID_COLUMN).
        embedding_column (str): Name of the embedding column (default: POSTGRES_VECTOR_STORE_EMBEDDING_COLUMN).
        metadata_columns (str | list[str]): Comma-separated string or list of metadata column names.
    """
    if POSTGRES_TABLES_CONFIG_JSON:
        try:
            tables = json.loads(POSTGRES_TABLES_CONFIG_JSON)
            for table in tables:
                # Normalize metadata_columns to a list
                mc = table.get("metadata_columns", VECTOR_STORE_METADATA_COLUMNS)
                table["metadata_columns"] = mc.split(",") if isinstance(mc, str) else mc
                table.setdefault("id_column", VECTOR_STORE_ID_COLUMN)
                table.setdefault("embedding_column", VECTOR_STORE_EMBEDDING_COLUMN)
                table.setdefault("description", f"PostgreSQL vector store table: {table['name']}")
            return tables
        except Exception as e:
            logger.error(f"Error parsing POSTGRES_TABLES_CONFIG: {e}")

    # Fall back to the legacy single-table configuration
    if VECTOR_STORE_TABLE:
        return [
            {
                "name": VECTOR_STORE_TABLE,
                "description": f"PostgreSQL vector store table: {VECTOR_STORE_TABLE}",
                "id_column": VECTOR_STORE_ID_COLUMN,
                "embedding_column": VECTOR_STORE_EMBEDDING_COLUMN,
                "metadata_columns": VECTOR_STORE_METADATA_COLUMNS,
            }
        ]
    return []


TABLES_CATALOG: list[dict] = _load_tables_catalog()

ADA = "text-embedding-ada-002"
TE_SMALL = "text-embedding-3-small"

# OPENAI CONSTANTS
POSTGRES_EMBEDDING_DEPLOYMENT = os.getenv(
    "POSTGRES_EMBEDDING_DEPLOYMENT", TE_SMALL
)  # Azure deployment name
OPENAI_KEY = os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("POSTGRES_OPENAI_BASE_URL")
OPENAI_API_VERSION = os.getenv("POSTGRES_OPENAI_API_VERSION")  # Use your Azure OpenAI API version

# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

postgres_router = FastMCP(name="Postgres Vector Search Service")

# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================


def get_embedding_service() -> AzureOpenAIEmbeddings:
    """
    Helper function to get an AzureOpenAIEmbeddings instance.
    Returns:
        AzureOpenAIEmbeddings: An embedding service instance.
    """
    return AzureOpenAIEmbeddings(
        model=POSTGRES_EMBEDDING_DEPLOYMENT,
        api_key=OPENAI_KEY,
        azure_endpoint=OPENAI_BASE_URL,
        api_version=OPENAI_API_VERSION,
        azure_deployment=POSTGRES_EMBEDDING_DEPLOYMENT,
    )


def get_table_config(table_name: str | None = None) -> dict:
    """
    Return the configuration dict for a named table.
    If table_name is None, the first table in the catalog is returned.

    Args:
        table_name: Name of the table to look up, or None to use the default.

    Returns:
        Table configuration dictionary.

    Raises:
        ValueError: If the catalog is empty or the table is not found.
    """
    if not TABLES_CATALOG:
        raise ValueError(
            "No PostgreSQL tables configured. "
            "Set POSTGRES_TABLES_CONFIG or POSTGRES_VECTOR_STORE_TABLE."
        )
    if table_name is None:
        return TABLES_CATALOG[0]
    for table in TABLES_CATALOG:
        if table["name"] == table_name:
            return table
    raise ValueError(
        f"Table '{table_name}' not found in the catalog. "
        "Use postgres_list_tables to see available tables."
    )


async def get_pg_vector_store(table_name: str | None = None) -> PGVectorStore:
    """
    Helper function to get a PGVectorStore instance.

    Args:
        table_name: Name of the table to connect to. Defaults to the first
            table in the catalog.

    Returns:
        PGVectorStore: A PGVectorStore instance connected to the PostgreSQL database.
    """
    config = get_table_config(table_name)
    pg_engine = PGEngine.from_connection_string(DB_CONN)

    embedding_service = get_embedding_service()

    # Create and return the PGVectorStore instance
    vector_store = await PGVectorStore.create(
        engine=pg_engine,
        table_name=config["name"],
        embedding_service=embedding_service,
        id_column=config["id_column"],
        metadata_columns=config["metadata_columns"],
    )

    return vector_store


def convert_filter_dates(filter_dict: dict | None) -> dict | None:
    """
    Recursively convert date strings to datetime objects in a filter dictionary.

    Args:
        filter_dict: The filter dictionary that may contain date strings

    Returns:
        Filter dictionary with date strings converted to datetime objects
    """
    if not filter_dict:
        return filter_dict

    def convert_value(value):
        if isinstance(value, str):
            # Try to parse common date/datetime formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [convert_value(v) for v in value]
        return value

    return convert_value(filter_dict)


# endregion
# ============================================================================

# ============================================================================
# region TOOLS
# ============================================================================


@postgres_router.tool
async def postgres_list_tables() -> list[dict]:
    """
    Tool to list all available PostgreSQL tables with their descriptions.
    Use this tool first to discover which tables are available before
    performing a search or retrieving a schema.
    Returns:
        List of dictionaries with 'name' and 'description' for each table.
    """
    return [
        {"name": table["name"], "description": table["description"]} for table in TABLES_CATALOG
    ]


@postgres_router.tool
async def postgres_vector_search(
    query: str,
    search_filter: dict | None,
    table_name: str | None = None,
    score_threshold: float | None = None,
) -> list:
    """
    Tool to perform a vector search in PostgreSQL using pgvector.
    Args:
        query (str): The search query. TIP: Extract key concepts from the user's question.
            For example, if the user asks for 'buildings near a river', use 'buildings river' as the query.
        search_filter (dict | None): Optional filter to apply before vector search.
            IMPORTANT: Ensure filter values match the column data types in the database.
            Use 'postgres_get_table_schema' to check column types. For example, if 'site_id'
            is stored as TEXT/VARCHAR, use string values like {'site_id': {'$eq': '4107120'}}
            not integers like {'site_id': {'$eq': 4107120}}.
        table_name (str | None): Name of the table to search. Use 'postgres_list_tables' to
            see available tables. Defaults to the first configured table.
        score_threshold (float | None): Minimum similarity score (0.0 to 1.0) a result must meet to be returned. Lower values (e.g., 0.2) return more results with looser matches; higher values (e.g., 0.6) return fewer, more relevant results. If omitted, the server default threshold is used.
    Returns:
        List of relevant records matching the query.
    """

    start_time = time.time()

    logger.info(
        f"from postgres_vector_search: query={query}, "
        f"filter={search_filter}, table_name={table_name}"
    )

    # Convert date strings to datetime objects
    search_filter = convert_filter_dates(search_filter)

    try:
        vector_store = await get_pg_vector_store(table_name)
        embedding_service = get_embedding_service()

        # Handle empty query case - when doing pure metadata filtering
        # we use a placeholder query but disable score threshold
        effective_query = query if query.strip() else "general search"
        use_score_threshold = bool(query.strip())

        query_vector = embedding_service.embed_query(effective_query)

        search_kwargs = {
            "k": CONTEXT_COUNT,
            "filter": search_filter,
        }

        # Only apply score threshold if there's an actual semantic query
        if use_score_threshold:
            search_kwargs["score_threshold"] = (
                score_threshold if score_threshold is not None else VECTOR_SEARCH_SCORE_THRESHOLD
            )

        docs = await vector_store.asimilarity_search_by_vector(query_vector, **search_kwargs)
        logger.info(f"postgres_vector_search found {len(docs)} documents.")
        return docs

    except Exception as e:
        logger.error("Error in postgres_vector_search", exc_info=True)
        return [f"Error: {e!s}"]
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"postgres_vector_search completed in {elapsed_time:.2f} seconds.")


@postgres_router.tool
async def postgres_vector_find_one(
    query: str,
    search_filter: dict | None,
    table_name: str | None = None,
) -> dict | None:
    """
    Tool to find a single record in PostgreSQL using vector search. Use this to see sample data for a query to help with
    filter creation and query refinement.
    Args:
        query (str): The search query.
        search_filter (dict | None): Optional filter to apply before vector search.
        table_name (str | None): Name of the table to search. Use 'postgres_list_tables' to
            see available tables. Defaults to the first configured table.
    Returns:
        A single relevant record matching the query or None if not found.
    """
    start_time = time.time()

    logger.info(
        f"from postgres_vector_find_one: query={query}, "
        f"filter={search_filter}, table_name={table_name}"
    )

    # Convert date strings to datetime objects
    search_filter = convert_filter_dates(search_filter)

    try:
        vector_store = await get_pg_vector_store(table_name)
        embedding_service = get_embedding_service()
        query_vector = embedding_service.embed_query(query)
        doc = await vector_store.asimilarity_search_by_vector(
            query_vector, k=1, filter=search_filter, score_threshold=0.4
        )

        if doc:
            return doc[0]
        else:
            return None

    except Exception as e:
        logger.error("Error in postres_vector_find_one", exc_info=True)
        return {"error": str(e)}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"postgres_vector_find_one completed in {elapsed_time:.2f} seconds.")


@postgres_router.tool
async def postgres_get_table_schema(table_name: str | None = None) -> dict:
    """
    Tool to get the schema information of a PostgreSQL vector store table.
    Args:
        table_name (str | None): Name of the table whose schema to retrieve. Use
            'postgres_list_tables' to see available tables. Defaults to the first
            configured table.
    Returns:
        Dictionary containing table schema information including columns, their types,
        nullable status, defaults, and metadata columns configuration.
    """
    start_time = time.time()

    config = get_table_config(table_name)
    resolved_table = config["name"]
    logger.info(f"from postgres_get_table_schema: table_name={resolved_table}")

    try:
        from psycopg import AsyncConnection

        # Get database connection
        conn = await AsyncConnection.connect(DB_CONN.replace("+asyncpg://", "://"))

        # Query to get column information from information_schema
        query = """
            SELECT 
                column_name, 
                data_type, 
                is_nullable, 
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """

        async with conn.cursor() as cur:
            await cur.execute(query, (resolved_table,))
            rows = await cur.fetchall()
            colnames = [desc[0] for desc in cur.description]

            columns = []
            for row in rows:
                col_info = dict(zip(colnames, row, strict=True))
                columns.append(col_info)

        await conn.close()

        schema_info = {
            "table_name": resolved_table,
            "columns": columns,
            "id_column": config["id_column"],
            "embedding_column": config["embedding_column"],
        }

        return schema_info

    except Exception as e:
        logger.error("Error in postgres_get_table_schema", exc_info=True)
        return {"error": str(e)}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"postgres_get_table_schema completed in {elapsed_time:.2f} seconds.")


# endregion
# ============================================================================

# ============================================================================
# region RESOURCES
# ============================================================================


@postgres_router.resource(uri="resource://postgres_service/postgres_filter_info")
async def postgres_filter_info() -> str:
    """
    Resource providing information about PostgreSQL Filter clause usage for filtering.
    Returns:
        A string with information about PostgreSQL filter objects.
    """

    # Get the directory of the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    md_file_path = os.path.join(current_dir, "postres_filter.md")

    fallback_message = (
        "Postgres filters are objects that pre-filter documents before performing vector searches."
    )

    try:
        with open(md_file_path, encoding="utf-8") as f:
            file_contents = f.read()
            return file_contents
    except FileNotFoundError:
        return fallback_message


# endregion
# ============================================================================

# ============================================================================
# region PROMPTS
# ============================================================================


@postgres_router.prompt(name="postgres_vector_search_prompt")
def postgres_vector_search_prompt() -> str:
    """
    Prompt template for PostgreSQL vector search tool.
    Returns:
        A string prompt template.
    """
    return (
        "You are a helpful assistant that performs vector searches in a PostgreSQL database with pgvector extension. "
        "Given a user query, explore the database structure, identify relevant tables, and return relevant records. "
        "Use the available PostgreSQL tools to perform searches and retrieve information.\n\n"
        "### Available Tools:\n"
        "- 'postgres_list_tables' : List all available tables with descriptions. Call this first to discover which tables are available.\n"
        "- 'postgres_vector_search' : Perform vector similarity search. include a filter object when possible to improve query response accuracy and speed.\n"
        "  - The 'query' parameter should be a concise representation of the user's question, focusing on key concepts, for example:\n"
        "    - If the user asks for 'riverside buildings within 0.5 miles of Providence, RI.', use 'building river' as the query.\n"
        "  - The 'table_name' parameter specifies which table to search (use the name returned by 'postgres_list_tables').\n"
        "- 'postgres_vector_find_one' : Find a single record to see sample data for filter creation and query refinement.\n"
        "  - The 'table_name' parameter specifies which table to search.\n"
        "- 'postgres_get_table_schema' : Get the schema information of a table including columns, id_column and embedding_column.\n"
        "  - The 'table_name' parameter specifies which table's schema to retrieve.\n\n"
        "### Instructions:\n"
        "1. Use 'postgres_list_tables' to discover all available tables and choose the most relevant one(s).\n"
        "2. Use 'postgres_get_table_schema' to understand the table structure and available columns for filtering.\n"
        "3. Think about the user's request and how best to formulate the query and filter.\n"
        "4. Build a filter object based on the table schema to narrow down the search results.\n"
        "   - IMPORTANT: Match filter value types to column data types. If a column is TEXT/VARCHAR, use string values (e.g., '4107120'), not integers.\n"
        "5. Use 'postgres_vector_search' with the user query, the constructed filter, and the chosen table_name to find relevant records.\n"
        "6. If necessary, use 'postgres_vector_find_one' to retrieve a sample record for filter refinement.\n"
        "7. Analyze the returned records for relevance to the user query.\n"
        "8. If the records are not relevant, refine the filter and repeat the search process.\n\n"
        "### Response Guidelines:\n"
        "- Always provide accurate and relevant information based on the search results.\n"
        "- Always check the results against the user's query for relevance. If results are outside of a user's specified parameters (e.g., location, date range), refine your search.\n\n"
        "### CRITICAL - NO RESULTS BEHAVIOR:\n"
        "- It is OKAY to leave the 'query' parameter empty if you are using only filters to find results.\n"
        "  For example: The user asks for 'all documents with site id 1234': filter = { \"\\$and\": [ { \"site_id\": 1234 } ] } and query = '' \n"
        "- If the user asks for results near a specific location or within a date range, ensure that the results strictly adhere to those parameters, using appropriate filters.\n"
        "- NEVER MAKE UP, FABRICATE, OR INVENT DATA. ONLY USE ACTUAL RESULTS FROM THE TOOLS.\n"
        "- If the tools return empty results or no matching records, you MUST explicitly tell the user: 'No matching records were found in the database.'\n"
        "- Do NOT create placeholder, dummy, or example data to fill in gaps.\n"
        "- Do NOT use your general knowledge to fabricate database records that don't exist.\n"
        "- If you are unsure whether results are real, ask the user to clarify or refine their query.\n"
        f"### NOTE: Limit the number of calls to the 'postgres_vector_search' tool to a maximum of {VECTOR_SEARCH_MAX_ATTEMPTS} attempts per user query. \n"
        "Notify the user that you have reached the maximum number of attempts if applicable, giving them the option to run more queries.\n\n"
    )


# endregion
# ============================================================================
