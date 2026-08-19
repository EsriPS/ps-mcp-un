"""
MongoDB Vector Search Service.

This module provides tools for interacting with MongoDB for vector search operations.
"""

# ============================================================================
# CONFIGURATION
# ============================================================================

import logging
import os
import time

from fastmcp import FastMCP
from openai import AsyncAzureOpenAI
from pymongo import AsyncMongoClient

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

# Define any constants needed for the service
DB_CONN = os.getenv("MONGO_DB_CONN")
DB_NAME = os.getenv("MONGO_DB_NAME")
CONTEXT_COUNT = int(os.getenv("CONTEXT_COUNT", "20"))
CANDIDATES_MULTIPLIER = int(os.getenv("CANDIDATES_MULTIPLIER", "15"))

ADA = "text-embedding-ada-002"
TE_SMALL = "text-embedding-3-small"

# OPENAI CONSTANTS
EMBEDDING_DEPLOYMENT = os.getenv("EMBEDDING_DEPLOYMENT", ADA)  # Azure deployment name
OPENAI_KEY = os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("MONGO_OPENAI_BASE_URL")
OPENAI_API_VERSION = os.getenv(
    "MONGO_OPENAI_API_VERSION", "2024-10-21"
)  # Use your Azure OpenAI API version

# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

mongo_router = FastMCP(name="Mongo Vector Search Service")

# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================

# Add helper functions for MongoDB operations here

# endregion
# ============================================================================

# ============================================================================
# region TOOLS
# ============================================================================


@mongo_router.tool
async def mongo_vector_search(
    collection_name: str, query: str, vector_search_index: str, search_filter: dict | None
) -> list:
    """
    Tool to perform a vector search in MongoDB.
    Args:
        collection_name (str): The name of the MongoDB collection to search.
        query (str): The search query.
        vector_search_index (str): The name of the vector search index to use.
        search_filter (dict): Filter to apply. Use empty dict {} if no filter needed.
                                     Providing a filter significantly improves performance.
    Returns:
        List of relevant document contents matching the query.
    """
    start_time = time.time()

    if search_filter is None:
        search_filter = {}
    logger.info(
        f"from mongo_vector_search: collection_name={collection_name}, query={query}, "
        f"vector_search_index={vector_search_index}, search_filter={search_filter}"
    )

    results = []
    try:
        mongo_client = AsyncMongoClient(DB_CONN)
        collection = mongo_client.get_database(DB_NAME).get_collection(collection_name)

        # Create OpenAI Client and generate embedding for the query
        client = AsyncAzureOpenAI(
            api_key=OPENAI_KEY, azure_endpoint=OPENAI_BASE_URL, api_version=OPENAI_API_VERSION
        )
        embedding_response = await client.embeddings.create(
            input=[query], model=EMBEDDING_DEPLOYMENT
        )
        query_embedding = embedding_response.data[0].embedding

        pipeline = [
            {
                "$vectorSearch": {
                    "index": vector_search_index,
                    "queryVector": query_embedding,
                    "path": "embedding",
                    "filter": search_filter,
                    "numCandidates": CONTEXT_COUNT * CANDIDATES_MULTIPLIER,
                    "limit": CONTEXT_COUNT,
                },
            },
            {
                "$project": {
                    "_id": 0,
                    "text": 1,
                    "text_info": 1,
                    "metadata": 1,
                },
            },
        ]

        documents = await collection.aggregate(pipeline)
        async for document in documents:
            # Append each document to results but remove the embedding field if it exists
            if "embedding" in document:
                document.pop("embedding")
            results.append(document)

    except Exception as e:
        logger.error("Error in mongo_vector_search", exc_info=True)
        results.append({"error": str(e)})
    finally:
        elapsed_time = time.time() - start_time
        logger.info(
            f"mongo_vector_search completed in {elapsed_time:.2f} seconds. Returned {len(results)} results."
        )

    return results


@mongo_router.tool
async def mongo_list_collections() -> list:
    """
    Tool to list all collections in the MongoDB database.
    Returns:
        List of collection names.
    """
    start_time = time.time()

    logger.info("mongo_list_collections called")
    try:
        mongo_client = AsyncMongoClient(DB_CONN)
        db = mongo_client.get_database(DB_NAME)
        collection_names = await db.list_collection_names()
        return collection_names
    except Exception as e:
        logger.error("Error in mongo_list_collections", exc_info=True)
        return [f"Error: {e!s}"]
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"mongo_list_collections completed in {elapsed_time:.2f} seconds.")


@mongo_router.tool
async def mongo_get_collection_info(collection_name: str) -> dict:
    """
    Tool to get information about a specific MongoDB collection.
    Args:
        collection_name (str): The name of the collection.
    Returns:
        Dictionary with collection information.
    """
    start_time = time.time()

    logger.info(f"from mongo_get_collection_info: collection_name={collection_name}")
    try:
        mongo_client = AsyncMongoClient(DB_CONN)
        db = mongo_client.get_database(DB_NAME)
        collection = db.get_collection(collection_name)
        options = await collection.options()

        return options if options else {"message": "No options found for this collection."}
    except Exception as e:
        logger.error("Error in mongo_get_collection_info", exc_info=True)
        return {"error": str(e)}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"mongo_get_collection_info completed in {elapsed_time:.2f} seconds.")


@mongo_router.tool
async def mongo_collection_find_one(collection_name: str, search_filter: dict | None) -> dict:
    """
    Tool to find one document in a specific MongoDB collection based on a filter.
    Args:
        collection_name (str): The name of the collection.
        search_filter (dict): The filter to apply for the search. Supply empty dict {} to get any document.
    Returns:
        The found document or an error message.
    """
    start_time = time.time()

    logger.info(
        f"from mongo_collection_find_one: collection_name={collection_name}, search_filter={search_filter}"
    )
    try:
        mongo_client = AsyncMongoClient(DB_CONN)
        db = mongo_client.get_database(DB_NAME)
        collection = db.get_collection(collection_name)

        document = await collection.find_one(search_filter or {})
        if document:
            # Convert ObjectId and other BSON types to JSON-serializable formats
            if "_id" in document:
                document["_id"] = str(document["_id"])
            return document
        else:
            return {"message": "No document found matching the filter."}
    except Exception as e:
        logger.error("Error in mongo_collection_find_one", exc_info=True)
        return {"error": str(e)}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"mongo_collection_find_one completed in {elapsed_time:.2f} seconds.")


@mongo_router.tool
async def mongo_collection_get_indexes(collection_name: str) -> dict | str:
    """
    Tool to get the indexes of a specific MongoDB collection.
    Args:
        collection_name (str): The name of the collection.
    Returns:
        A dict containing: vector_search_indexes (list of vector search index names) and indexed_fields (list of indexed field names), or an error message.
    """
    start_time = time.time()

    logger.info(f"from mongo_collection_get_indexes: collection_name={collection_name}")
    try:
        mongo_client = AsyncMongoClient(DB_CONN)
        db = mongo_client.get_database(DB_NAME)
        collection = db.get_collection(collection_name)

        # indexes = await collection.index_information()
        indexed_fields = []
        # for each value in the indexes dict, get the 'key' property (which is a list of tuples) and extract the field names
        # for index in indexes.values():
        #     fields = [field[0] for field in index['key']]
        #     indexed_fields.extend(fields)

        search_indexes = await (await collection.list_search_indexes()).to_list()
        vector_indexes = []
        for search_index in search_indexes:
            if search_index["type"] == "vectorSearch":
                vector_indexes.append(search_index["name"])
            for field in search_index["latestDefinition"]["fields"]:
                if field["type"] == "filter":
                    indexed_fields.append(field["path"])
        return {"indexed_fields": indexed_fields, "vector_search_indexes": vector_indexes}
    except Exception as e:
        logger.error("Error in mongo_collection_get_indexes", exc_info=True)
        return str(e)
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"mongo_collection_get_indexes completed in {elapsed_time:.2f} seconds.")


# endregion
# ============================================================================

# ============================================================================
# region RESOURCES
# ============================================================================


@mongo_router.resource(uri="resource://mongo_service/mongo_filter_info")
async def mongo_filter_info() -> str:
    """
    Resource providing information about MongoDB filter usage.
    Returns:
        A string with information about MongoDB filters.
    """

    # Get the directory of the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    md_file_path = os.path.join(current_dir, "mongo_pre_filter.md")

    fallback_message = (
        "MongoDB filters allow you to specify criteria to narrow down search results. "
        "You can use various operators to build complex queries. "
        "Refer to the MongoDB documentation for more details."
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


@mongo_router.prompt()
def mongo_vector_search_prompt() -> str:
    """
    Prompt template for MongoDB vector search tool.
    Returns:
        A string prompt template.
    """
    return (
        "You are a helpful assistant that performs vector searches in a MongoDB collection. "
        "Given a user query, generate an appropriate search filter if needed, and return relevant documents. "
        "Use the 'mongo_vector_search' tool to perform the search."
        "Use the 'mongo_list_collections' tool to see available collections to help find the correct one(s) based on the user query."
        "Use the 'mongo_get_collection_info' tool to get information about a specific collection."
        "Use the 'mongo_collection_find_one' tool to find a sample document in a collection to help construct search_filter."
        "Use the 'mongo_collection_get_indexes' tool to get vector_search_indexes for the 'mongo_vector_search' tool and indexed fields in a collection to help construct search_filter."
        "### Instructions:\n"
        "- If the user does not specify a collection, start by listing the available collections to find the most relevant one(s) for the user's query.\n"
        "- Next you need to use the 'mongo_collection_get_indexes' tool to get the vector search indexes and indexed fields for the collection(s) you identified.\n"
        "- If necessary, get collection info or sample documents to understand the data structure.\n"
        "- ***ALWAYS*** construct a search_filter for the 'mongo_vector_search' tool based on the user's query and the collection's indexed fields, it will make the query MUCH faster!!!\n"
        "- If there are no indexed fields, or a filter does not improve relevance, you may perform the search passing an empty dict for the search_filter.\n"
        "- **ALWAYS** make sure to get a valid vector_search_index from the 'mongo_collection_get_indexes' tool to use in the 'mongo_vector_search' tool.\n"
        "- When building a filter, make sure to include the entire field name as it appears in the document (including nested fields if applicable) and NEVER use a field that isn't in the results of mongo_collection_get_indexes.\n"
        "- Perform the vector search using the constructed filter and evaluate the returned documents.\n"
        "- If the returned documents are not relevant, refine the search filter and try again.\n"
        "- Provide the user with the most relevant documents found.\n"
        "- If no relevant documents are found, inform the user accordingly.\n\n"
        "### NOTE: Limit the number of calls to the 'mongo_vector_search' tool to a maximum of 5 attempts per user query. \n"
        "Notify the user that you have reached the maximum number of attempts if applicable, giving them the option to run more queries.\n\n"
        "### Output Format:\n"
        "When providing the final output, always include links to source documents if available.\n"
    )


# endregion
# ============================================================================
