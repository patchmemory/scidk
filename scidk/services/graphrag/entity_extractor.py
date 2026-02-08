"""
Generic entity extraction for GraphRAG queries.
Extracts structured entities from natural language, but doesn't assume specific schema.
"""
from typing import Dict, List, Optional, Any
import re
import os


class EntityExtractor:
    """
    Extract entities from natural language queries.
    Schema-agnostic: extracts generic patterns (IDs, names, types) without hardcoding node labels.
    """

    def __init__(self, anthropic_api_key: Optional[str] = None):
        """
        Initialize entity extractor.

        Args:
            anthropic_api_key: Optional Anthropic API key for LLM-based extraction.
                              Falls back to pattern matching if not provided.
        """
        self.anthropic_api_key = anthropic_api_key or os.environ.get('SCIDK_ANTHROPIC_API_KEY')
        self.use_llm = bool(self.anthropic_api_key)

    def extract(self, query: str, schema_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract entities from natural language query.

        Args:
            query: Natural language query
            schema_context: Optional schema info (labels, relationships) for context

        Returns:
            Dict with extracted entities: {
                'identifiers': [...],  # IDs, UIDs, codes
                'labels': [...],       # Potential node labels mentioned
                'properties': {...},   # Property filters (name=X, type=Y)
                'intent': str,         # Query intent (find, count, show, list)
            }
        """
        if self.use_llm and schema_context:
            return self._extract_with_llm(query, schema_context)
        return self._extract_with_patterns(query, schema_context)

    def _extract_with_patterns(self, query: str, schema_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pattern-based entity extraction (fallback when no LLM).
        Extracts generic patterns without assuming specific schema.
        """
        entities = {
            'identifiers': [],
            'labels': [],
            'properties': {},
            'intent': 'find',
        }

        # Extract identifiers (IDs, UIDs, codes)
        # Patterns: uppercase+numbers, quoted strings, specific ID formats
        id_patterns = [
            r'\b([A-Z]{2,}[_-]?[0-9]{3,})\b',  # e.g., NHP123, SEQ_001
            r'\b([A-Z]+[0-9]+)\b',              # e.g., A001, S123
            r'["\']([^"\']+)["\']',             # Quoted strings
        ]
        for pattern in id_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            entities['identifiers'].extend(matches)

        # Detect intent (most specific first)
        query_lower = query.lower()
        if any(word in query_lower for word in ['count', 'how many', 'number of']):
            entities['intent'] = 'count'
        elif any(word in query_lower for word in ['list', 'every']):
            entities['intent'] = 'list'
        elif any(word in query_lower for word in ['show', 'display', 'view']):
            entities['intent'] = 'show'
        elif any(word in query_lower for word in ['find', 'search', 'look for', 'get']):
            entities['intent'] = 'find'

        # Match against known labels from schema
        if schema_context and 'labels' in schema_context:
            for label in schema_context['labels']:
                # Case-insensitive match - try both exact and plural forms
                if re.search(r'\b' + re.escape(label) + r's?\b', query, re.IGNORECASE):
                    if label not in entities['labels']:
                        entities['labels'].append(label)

        # Extract property filters (name=X, type=Y, etc.)
        # Look for patterns like "name is X", "type: Y", "called X", "with name=X"
        property_patterns = [
            (r'(?:name|called)\s+(?:is|=|:)\s*["\']?([^"\'\s,]+)["\']?', 'name'),
            (r'(?:with|having)\s+name\s*=\s*["\']?([^"\'\s,]+)["\']?', 'name'),
            (r'type\s*(?:is|=|:)\s*["\']?([^"\'\s,]+)["\']?', 'type'),
        ]
        for pattern, prop_name in property_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and len(value) > 0:
                    entities['properties'][prop_name] = value

        return entities

    def _extract_with_llm(self, query: str, schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM-based entity extraction with schema context.
        More accurate but requires API call.
        """
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.anthropic_api_key)

            # Build prompt with schema context
            labels_str = ', '.join(schema_context.get('labels', []))
            rels_str = ', '.join(schema_context.get('relationships', []))

            prompt = f"""Extract structured information from this graph database query.

Available Schema:
- Node Labels: {labels_str}
- Relationships: {rels_str}

User Query: "{query}"

Extract and return as JSON:
{{
    "identifiers": ["list", "of", "IDs", "or", "codes"],
    "labels": ["matching", "node", "labels"],
    "properties": {{"property_name": "value"}},
    "intent": "find|count|show|list"
}}

Rules:
- Only include labels that exist in the schema
- Identifiers are IDs, codes, UIDs mentioned in query
- Properties are name/type/status filters
- Intent is the main action (find, count, show, list)

Return ONLY the JSON, no explanation."""

            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            import json
            response_text = message.content[0].text.strip()
            # Handle markdown code blocks
            if '```' in response_text:
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            entities = json.loads(response_text)
            return entities

        except Exception as e:
            # Fall back to pattern matching
            print(f"LLM extraction failed: {e}, falling back to patterns")
            return self._extract_with_patterns(query, schema_context)
