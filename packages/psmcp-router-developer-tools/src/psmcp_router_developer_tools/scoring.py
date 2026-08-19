"""Shared relevance scoring for code sample search."""


def compute_relevance(content: str, file_path: str, query_terms: list[str]) -> float:
    """Compute a relevance score based on term frequency in content and path.

    Path matches are weighted higher (3.0 per term) to prioritize files whose
    names relate to the query. Content matches are capped at 10 per term to
    avoid over-weighting large files.

    Args:
        content: File content (will be lowercased internally).
        file_path: Relative file path (will be lowercased internally).
        query_terms: Pre-lowercased search terms.

    Returns:
        Score >= 0. Higher means more relevant.
    """
    content_lower = content.lower()
    path_lower = file_path.lower()
    score = 0.0

    for term in query_terms:
        if term in path_lower:
            score += 3.0
        count = content_lower.count(term)
        if count > 0:
            score += min(count, 10)

    return score
