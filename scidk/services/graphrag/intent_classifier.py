"""
Intent classification for GraphRAG routing.

Routes user queries between two execution paths:
- LOOKUP: Fast Text2Cypher path for specific data retrieval queries
- REASONING: Full GraphRAG with LLM reasoning for analytical/synthesis queries

Uses regex-based pattern matching for Sprint 1. Can be replaced with
model-based classification in Sprint 2 without changing the interface.
"""
import re
from enum import Enum


class Intent(Enum):
    """Query intent types for routing."""
    LOOKUP = "lookup"       # Fast path: Text2Cypher for specific data queries
    REASONING = "reasoning"  # Reasoning path: Full LLM with graph context


# Patterns for LOOKUP intent (specific data retrieval)
LOOKUP_PATTERNS = [
    r"\bhow many\b",
    r"\bshow me\b",
    r"\blist\b",
    r"\bfind\b",
    r"\bcount\b",
    r"\bget\b",
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bwhen was\b",
    r"\bwhich\b",
    r"\bwhere is\b",
    r"\bwho is\b",
    r"\bgive me\b",
    r"\bfetch\b",
    r"\bretrieve\b",
]

# Patterns for REASONING intent (analysis/synthesis)
REASONING_PATTERNS = [
    r"\bwhy\b",
    r"\bexplain\b",
    r"\bcompare\b",
    r"\bsummariz[e"]?\b",
    r"\bwhat.s the state\b",
    r"\bhelp me understand\b",
    r"\bwhat should\b",
    r"\banalyze\b",
    r"\btell me about\b",
    r"\bdescribe\b",
    r"\binterpret\b",
    r"\brelationship between\b",
    r"\bhow (?:do|does|did)\b",  # "how do X work" vs "how many X"
    r"\binsights?\b",
    r"\btrends?\b",
]


def classify(message: str) -> Intent:
    """
    Classify user message intent for routing.

    Args:
        message: Natural language query from user

    Returns:
        Intent.LOOKUP for specific data retrieval queries
        Intent.REASONING for analytical/synthesis queries

    Priority: REASONING patterns checked first (more specific).
    Default: REASONING for ambiguous cases (safer to use full LLM).
    """
    msg_lower = message.lower()

    # Check REASONING patterns first (higher priority)
    for pattern in REASONING_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.REASONING

    # Check LOOKUP patterns
    for pattern in LOOKUP_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.LOOKUP

    # Default to REASONING for safety (handles open-ended questions)
    return Intent.REASONING
