"""
Dataset summarization for GraphRAG SUMMARIZE intent.

Generates comprehensive overviews of knowledge graph data by running
count queries and synthesizing results into narrative form.
"""
from typing import Dict, Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


def generate_summary(driver, database: str, provider, schema_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a narrative summary of the knowledge graph dataset.

    Runs count queries for labels and relationships, then uses the LLM provider
    to synthesize a researcher-friendly overview. This is the handler for the
    SUMMARIZE intent path.

    Performance notes:
    - Caps label queries at 20 to avoid runaway queries on large schemas
    - Caps relationship queries at 20 for the same reason
    - Each count is a separate query for clarity and error handling
    - Total query count: 2 (for discovery) + up to 40 (20 labels + 20 rels)

    Args:
        driver: Neo4j driver instance
        database: Database name (e.g., "neo4j")
        provider: LLMProvider instance with .complete() method
        schema_context: Schema dict with 'labels', 'relationships', 'properties'

    Returns:
        Dict with:
            - status: 'ok' or 'error'
            - reply: Natural language summary narrative
            - metadata: Raw counts and statistics
            - execution_time_ms: Time taken for queries + synthesis
    """
    start_time = time.time()
    MAX_LABELS = 20
    MAX_RELATIONSHIPS = 20

    try:
        counts = {
            "labels": {},
            "relationships": {},
            "total_nodes": 0,
            "total_relationships": 0,
        }

        with driver.session(database=database) as session:
            # Discover all labels (but we'll only count the first MAX_LABELS)
            labels_result = session.run("CALL db.labels() YIELD label RETURN label LIMIT $limit", limit=MAX_LABELS)
            all_labels = [record["label"] for record in labels_result]

            # Discover all relationship types (cap at MAX_RELATIONSHIPS)
            rels_result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType LIMIT $limit",
                limit=MAX_RELATIONSHIPS
            )
            all_rels = [record["relationshipType"] for record in rels_result]

            # Count nodes per label
            for label in all_labels:
                try:
                    count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) as count")
                    count_value = count_result.single()["count"]
                    counts["labels"][label] = count_value
                    counts["total_nodes"] += count_value
                except Exception as e:
                    logger.warning(f"Failed to count label {label}: {e}")
                    counts["labels"][label] = 0

            # Count relationships per type
            for rel_type in all_rels:
                try:
                    count_result = session.run(f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) as count")
                    count_value = count_result.single()["count"]
                    counts["relationships"][rel_type] = count_value
                    counts["total_relationships"] += count_value
                except Exception as e:
                    logger.warning(f"Failed to count relationship {rel_type}: {e}")
                    counts["relationships"][rel_type] = 0

        # Build synthesis prompt for LLM
        synthesis_prompt = _build_synthesis_prompt(counts, schema_context)

        # Use provider to generate narrative summary
        # Note: We pass schema_context=None because we don't want schema details in the narrative
        # The counts dict IS the data we want the LLM to describe
        summary_text = provider.complete(
            user_message="Describe this knowledge graph dataset in plain language for a researcher.",
            system_prompt=synthesis_prompt,
            schema_context=None  # Don't include schema - we're describing data, not generating queries
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "status": "ok",
            "reply": summary_text,
            "engine": "summarize",  # For UI badge
            "metadata": {
                "label_counts": counts["labels"],
                "relationship_counts": counts["relationships"],
                "total_nodes": counts["total_nodes"],
                "total_relationships": counts["total_relationships"],
                "labels_analyzed": len(all_labels),
                "relationships_analyzed": len(all_rels),
                "capped_at": {
                    "labels": MAX_LABELS,
                    "relationships": MAX_RELATIONSHIPS
                },
                "execution_time_ms": elapsed_ms
            }
        }

    except Exception as e:
        logger.error(f"Summarization failed: {e}", exc_info=True)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "error",
            "error": str(e),
            "metadata": {
                "execution_time_ms": elapsed_ms
            }
        }


def _build_synthesis_prompt(counts: Dict[str, Any], schema_context: Dict[str, Any]) -> str:
    """
    Build system prompt for narrative synthesis.

    Args:
        counts: Dict with label_counts, relationship_counts, totals
        schema_context: Schema context (used for property info if available)

    Returns:
        System prompt string for synthesis
    """
    # Format counts for prompt
    label_lines = []
    for label, count in sorted(counts["labels"].items(), key=lambda x: x[1], reverse=True):
        label_lines.append(f"  - {label}: {count:,} nodes")

    rel_lines = []
    for rel_type, count in sorted(counts["relationships"].items(), key=lambda x: x[1], reverse=True):
        rel_lines.append(f"  - {rel_type}: {count:,} relationships")

    labels_str = "\n".join(label_lines) if label_lines else "  (No nodes found)"
    rels_str = "\n".join(rel_lines) if rel_lines else "  (No relationships found)"

    # Include property info if available
    props_info = ""
    properties = schema_context.get("properties", {})
    if properties:
        props_lines = []
        for label in list(counts["labels"].keys())[:10]:  # Top 10 labels only
            props = properties.get(label, [])
            if props:
                props_lines.append(f"  - {label}: {', '.join(props[:5])}")
        if props_lines:
            props_info = f"\n\nKey Properties by Label:\n" + "\n".join(props_lines)

    prompt = f"""You are a research data assistant describing a knowledge graph dataset to a scientist.

DATASET STATISTICS:
Total Nodes: {counts['total_nodes']:,}
Total Relationships: {counts['total_relationships']:,}

Node Counts by Label:
{labels_str}

Relationship Counts by Type:
{rels_str}{props_info}

TASK: Write a concise, informative summary (2-4 paragraphs) that:
1. Describes the overall size and scope of the dataset
2. Highlights the most prominent node types and their counts
3. Explains the main relationship patterns connecting the data
4. Mentions key data domains or subject areas (based on label names)
5. Notes any interesting patterns (e.g., highly connected nodes, sparse relationships)

STYLE:
- Write for a researcher who wants to understand what data is available to query
- Use clear, professional language - avoid jargon unless it's domain-specific
- Include specific numbers to give a sense of scale
- Be helpful and informative, not marketing-speak

Begin your summary now:"""

    return prompt
