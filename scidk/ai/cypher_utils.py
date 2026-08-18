"""
Cypher generation utilities for Neo4j query synthesis.

Provides system prompt construction and Cypher extraction from LLM responses.
"""
from typing import Dict, Any, Optional
import re


def build_cypher_system_prompt(schema_context: Dict[str, Any]) -> str:
    """
    Build a focused system prompt for Cypher query generation.

    This prompt is designed to generate executable Cypher queries without
    schema hallucination. Unlike the generic reasoning prompt, this one
    prioritizes precision and valid syntax over explanatory text.

    Args:
        schema_context: Schema dict with 'labels', 'relationships', 'properties'

    Returns:
        Complete system prompt string for Cypher generation
    """
    labels_str = ", ".join(schema_context.get("labels", []))
    rels_str = ", ".join(schema_context.get("relationships", []))

    # Format properties (show up to 5 per label for context)
    props_lines = []
    properties = schema_context.get("properties", {})
    for label in schema_context.get("labels", [])[:20]:  # Limit to top 20 labels
        props = properties.get(label, [])
        if props:
            props_lines.append(f"  - {label}: {', '.join(props[:5])}")

    props_str = "\n".join(props_lines) if props_lines else "  (No property info available)"

    prompt = f"""ROLE: You are a Neo4j Cypher expert embedded in a scientific research data platform.
Your job is to generate precise, executable Cypher queries from natural language questions.

RULES (enforce strictly):
1. ONLY use node labels, relationship types, and property names from the schema below
2. Never invent or guess property names - if a property doesn't exist in the schema, say so
3. Always RETURN the specific values the user asked about
4. For count questions ("how many X"), use COUNT() and return a single integer result
5. For listing questions ("show me X"), use LIMIT 50 unless the user specifies otherwise
6. Use DISTINCT where relationship traversal could create duplicate results
7. If the question cannot be answered with the available schema, respond with:
   "Cannot generate query: missing required labels or properties"
8. ⚠️  CRITICAL: Always filter on specific properties (n.property), NEVER on the node itself (n)
   WRONG: WHERE f CONTAINS 'CAC'
   CORRECT: WHERE f.name CONTAINS 'CAC'
9. For Folder searches: Check BOTH name AND path properties (folders often match in path but not name)
   CORRECT: WHERE f.name CONTAINS 'CAC' OR f.path CONTAINS 'CAC'
   Use single property only if user specifically says "name only" or "path only"
10. String length requires size(), not length().
    length() is ONLY for path lengths.
    WRONG: WHERE length(n.name) > 5
    RIGHT: WHERE size(n.name) > 5
    WRONG: substring(n.path, 0, length(n.path) - 4)
    RIGHT: substring(n.path, 0, size(n.path) - 4) 
11. When exploring relationships on an unknown node, ALWAYS start with
    an undirected pattern to discover all connections before assuming
    direction:
    
      CORRECT:   MATCH (s:Scan)-[r]-(n) RETURN DISTINCT type(r), labels(n)
      INCORRECT: MATCH (s:Scan)-[r]->(n) RETURN DISTINCT type(r), labels(n)
    
    Only use directed patterns once you know the direction from a prior
    undirected query or from the schema context. Never assume outgoing
    direction when the question is about discovery.

OUTPUT FORMAT:
- Return ONLY the Cypher query itself
- Do NOT include markdown code fences (no ```cypher or ```)
- Do NOT add explanation text before or after the query
- One query only - no multiple statements

AVAILABLE SCHEMA:
Node Labels: {labels_str}
Relationship Types: {rels_str}
Key Properties by Label:
{props_str}

COMMON PATTERNS:
- Counting nodes: MATCH (n:Label) RETURN count(n) AS total
- Filtering by property: MATCH (n:Label) WHERE n.property = 'value' RETURN n
- Traversing relationships: MATCH (a:A)-[:REL]->(b:B) RETURN a, b
- Aggregating: MATCH (n:Label)-[:REL]->(m) WITH n, count(m) AS m_count RETURN n, m_count ORDER BY m_count DESC
- Getting distinct values: MATCH (n:Label) RETURN DISTINCT n.property

Remember: Executable Cypher only. No explanations, no markdown, no apologies."""

    return prompt


def extract_cypher(response: str) -> Optional[str]:
    """
    Extract Cypher query from LLM response text.

    Handles multiple response formats:
    - Plain Cypher statements (MATCH ... RETURN ...)
    - Markdown code fences (```cypher ... ``` or ``` ... ```)
    - Cypher preceded or followed by explanatory text

    Args:
        response: Raw text response from LLM

    Returns:
        Extracted Cypher query string, or None if no valid Cypher found

    Examples:
        >>> extract_cypher("MATCH (n) RETURN count(n)")
        'MATCH (n) RETURN count(n)'

        >>> extract_cypher("```cypher\\nMATCH (n) RETURN n\\n```")
        'MATCH (n) RETURN n'

        >>> extract_cypher("Here's the query:\\nMATCH (n) RETURN n\\nThis finds all nodes.")
        'MATCH (n) RETURN n'
    """
    if not response or not response.strip():
        return None

    response = response.strip()

    # Strategy 1: Look for markdown code fences
    # Matches ```cypher\n...\n``` or ```\n...\n```
    fence_pattern = r"```(?:cypher)?\s*\n(.*?)\n```"
    fence_match = re.search(fence_pattern, response, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cypher_candidate = fence_match.group(1).strip()
        if _is_valid_cypher(cypher_candidate):
            return cypher_candidate

    # Strategy 2: Look for lines starting with Cypher keywords
    # Extract continuous block of Cypher-like statements
    cypher_keywords = [
        "MATCH", "OPTIONAL MATCH", "WITH", "RETURN", "WHERE", "CREATE",
        "MERGE", "DELETE", "REMOVE", "SET", "CALL", "UNWIND", "ORDER BY",
        "LIMIT", "SKIP", "UNION", "DISTINCT"
    ]

    lines = response.split('\n')
    cypher_lines = []
    capturing = False

    for line in lines:
        line_stripped = line.strip()
        line_upper = line_stripped.upper()

        # Start capturing if we hit a Cypher keyword
        if any(line_upper.startswith(kw) for kw in cypher_keywords):
            capturing = True
            cypher_lines.append(line_stripped)
        elif capturing:
            # Continue if line looks like Cypher continuation (has Cypher patterns)
            if (line_stripped and
                (any(kw in line_upper for kw in cypher_keywords) or
                 re.search(r'[\(\)\[\]\{\}\-\>]', line_stripped))):
                cypher_lines.append(line_stripped)
            else:
                # Stop capturing if we hit non-Cypher text
                break

    if cypher_lines:
        cypher_candidate = '\n'.join(cypher_lines)
        if _is_valid_cypher(cypher_candidate):
            return cypher_candidate

    # Strategy 3: If response looks entirely like Cypher (no explanatory sentences)
    # Check if the whole response is a valid query
    if _is_valid_cypher(response):
        return response

    # No valid Cypher found
    return None


def _is_valid_cypher(text: str) -> bool:
    """
    Heuristic check if text looks like valid Cypher.

    Not a full parser - just checks for basic Cypher structure:
    - Contains at least one Cypher keyword
    - Contains RETURN statement (required for read queries)
    - Has basic Cypher syntax patterns

    Args:
        text: Candidate Cypher string

    Returns:
        True if text appears to be Cypher, False otherwise
    """
    if not text or not text.strip():
        return False

    text_upper = text.upper()

    # Must contain at least MATCH or CREATE or MERGE or CALL
    has_start_keyword = any(kw in text_upper for kw in ["MATCH", "CREATE", "MERGE", "CALL"])
    if not has_start_keyword:
        return False

    # For read queries, must have RETURN
    # (CALL procedures might not, but those are rare in GraphRAG context)
    has_return = "RETURN" in text_upper

    # Check for basic Cypher syntax patterns
    has_cypher_patterns = bool(re.search(r'[\(\)\[\]\{\}\-\>]', text))

    # If it looks like natural language explanation, reject it
    # (sentences typically have spaces between words and punctuation)
    has_explanation_markers = bool(re.search(r'\b(?:the|this|that|here|query|will|can|should)\b', text, re.IGNORECASE))
    sentence_like = text.count('.') > 2 or text.count(',') > 5

    if has_explanation_markers and sentence_like:
        return False

    return has_return and has_cypher_patterns
