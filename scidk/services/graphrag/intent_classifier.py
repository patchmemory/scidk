"""
Intent classification for GraphRAG routing.

Routes user queries between execution paths:
- LOOKUP: Fast Text2Cypher path for specific data retrieval queries
- REASONING: Full GraphRAG with LLM reasoning for analytical/synthesis queries
- SUMMARIZE: Dataset overview with count queries
- REACT: Multi-step reasoning loop for exploratory/conditional queries

Uses regex-based pattern matching for Sprint 1. Can be replaced with
model-based classification in Sprint 2 without changing the interface.
"""
import re
from enum import Enum


class Intent(Enum):
    """Query intent types for routing."""
    LOOKUP = "lookup"       # Fast path: Text2Cypher for specific data queries
    REASONING = "reasoning"  # Reasoning path: Full LLM with graph context
    SUMMARIZE = "summarize"  # Summary path: Run count queries and synthesize overview
    REACT = "react"          # ReAct path: Multi-step reasoning with query execution


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

# Patterns for SUMMARIZE intent (dataset overview without specific target)
SUMMARIZE_PATTERNS = [
    r"\bsummariz[e]?\b.*\b(?:data|graph|dataset|knowledge base)\b",
    r"\boverview\b",
    r"\bwhat (?:do we|data do you|data do i) have\b",
    r"\bgive me (?:a picture|an overview)\b",
    r"\bhow much data\b",
    r"\bwhat.?s in (?:the |this )?(?:graph|database|dataset)\b",
    r"\bdescribe (?:the |this )?(?:graph|dataset|data)\b",
]

# Patterns for REASONING intent (analysis/synthesis)
REASONING_PATTERNS = [
    r"\bwhy\b",
    r"\bexplain\b",
    r"\bcompare\b",
    r"\bwhat.s the state\b",
    r"\bhelp me understand\b",
    r"\bwhat should\b",
    r"\banalyze\b",
    r"\binterpret\b",
    r"\bhow (?:do|does|did)\b",  # "how do X work" vs "how many X"
    r"\binsights?\b",
    r"\btrends?\b",
]

# Patterns for REACT intent (exploratory multi-step queries)
REACT_PATTERNS = [
    r"\btell me about\b",          # Exploratory: "tell me about samples"
    r"\bexplore\b",                 # Exploratory: "explore the relationships"
    r"\binvestigate\b",             # Exploratory: "investigate connections"
    r"\b(?:i'?m |i am )?curious about\b",  # Exploratory: "I'm curious about..."
    r"\bwhat can you (?:tell me|find)\b",   # Open-ended: "what can you tell me about X"
    r"\b(?:if|when|whether)\b.*\b(?:then|what|how)\b",  # Conditional: "if X then what"
    r"\b(?:which|what) ones?\b",    # Conditional subset: "which ones have X"
    r"\bare there any\b",           # Conditional existence: "are there any X that Y"
    r"\bshow me (?:all|everything)\b",  # Broad request needing filtering
    r"\bwhat type[s]? of \w+",      # Type queries: "what types of files"
    r"\blist.*type[s]?",            # List types: "list file types"
    r"\bwhat kind[s]? of",          # Kind queries: "what kinds of data"
    # Cross-service and multi-source patterns (Fix 2)
    r"\b(?:dropbox|sharepoint|google)\b",  # Service names: "CAC folders in Dropbox"
    r"\bacross\b.*\b(?:services?|sources?|platforms?)\b",  # "across all services"
    r"\ball (?:three|2|3)\b",       # "all three services"
    r"\beach (?:service|source|platform)\b",  # "each service"
    r"\bredundan[ct]",              # "redundant" or "redundancy"
    r"\bcompare\b.*\b(?:across|between)\b",  # "compare across services"
    r"\b(?:multi|multiple)[\s-](?:service|source|platform)\b",  # "multi-service query"
    r"\bcheck\b.*\b(?:all|each|every)\b",  # "check all services"
]


def classify(message: str) -> Intent:
    """
    Classify user message intent for routing.

    Args:
        message: Natural language query from user

    Returns:
        Intent.LOOKUP for specific data retrieval queries
        Intent.SUMMARIZE for dataset overview queries
        Intent.REACT for exploratory/conditional multi-step queries
        Intent.REASONING for analytical/synthesis queries

    Priority: SUMMARIZE > REACT > REASONING > LOOKUP.
    Default: REASONING for ambiguous cases (safer to use full LLM).
    """
    msg_lower = message.lower()

    # Check SUMMARIZE patterns first (most specific - dataset-level queries)
    for pattern in SUMMARIZE_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.SUMMARIZE

    # Check REACT patterns (exploratory queries that need multi-step reasoning)
    for pattern in REACT_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.REACT

    # Check REASONING patterns (higher priority than LOOKUP)
    for pattern in REASONING_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.REASONING

    # Check LOOKUP patterns
    for pattern in LOOKUP_PATTERNS:
        if re.search(pattern, msg_lower):
            return Intent.LOOKUP

    # Default to REASONING for safety (handles open-ended questions)
    return Intent.REASONING
