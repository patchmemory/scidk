"""
Schema-agnostic GraphRAG query engine for SciDK.
Combines entity extraction with neo4j-graphrag's Text2CypherRetriever.
"""
from typing import Dict, Any, Optional
import time


class QueryEngine:
    """
    High-level GraphRAG query interface.
    Schema-agnostic: works with any Neo4j database.
    """

    def __init__(
        self,
        driver: Any,
        neo4j_schema: Dict[str, Any],
        anthropic_api_key: Optional[str] = None,
        examples: Optional[list] = None,
        verbose: bool = False
    ):
        """
        Initialize query engine.

        Args:
            driver: Neo4j driver instance
            neo4j_schema: Schema dict with 'labels' and 'relationships'
            anthropic_api_key: Optional API key for entity extraction
            examples: Optional Text2Cypher examples
            verbose: If True, include extracted entities and Cypher in response
        """
        self.driver = driver
        self.neo4j_schema = neo4j_schema
        self.verbose = verbose
        self.examples = examples or []

        # Initialize entity extractor
        from .entity_extractor import EntityExtractor
        self.entity_extractor = EntityExtractor(anthropic_api_key)

    def query(self, question: str) -> Dict[str, Any]:
        """
        Execute natural language query against Neo4j.

        Args:
            question: Natural language question

        Returns:
            Dict with:
                - status: 'ok' or 'error'
                - answer: Natural language answer
                - entities: Extracted entities (if verbose)
                - cypher: Generated Cypher query (if verbose)
                - results: Raw results (if verbose)
                - execution_time_ms: Query execution time
        """
        start_time = time.time()

        try:
            # Step 1: Extract entities (with schema context)
            entities = self.entity_extractor.extract(question, self.neo4j_schema)

            # Step 2: Use neo4j-graphrag's Text2CypherRetriever
            try:
                from neo4j_graphrag.retrievers import Text2CypherRetriever
                from neo4j_graphrag.llm import LLMInterface

                # Create simple LLM wrapper if we have API key
                llm = None
                if self.entity_extractor.use_llm:
                    llm = self._create_llm_adapter()

                # Create retriever with schema
                retriever = Text2CypherRetriever(
                    driver=self.driver,
                    neo4j_schema=self.neo4j_schema,
                    examples=self.examples,
                    llm=llm
                )

                # Execute query
                result = retriever.search(query_text=question)

                # Format response
                execution_time = int((time.time() - start_time) * 1000)

                response = {
                    'status': 'ok',
                    'answer': self._format_answer(result, question),
                    'execution_time_ms': execution_time
                }

                if self.verbose:
                    response['entities'] = entities
                    response['results'] = result.items if hasattr(result, 'items') else []

                return response

            except ImportError:
                return {
                    'status': 'error',
                    'error': 'neo4j-graphrag not installed',
                    'hint': 'pip install neo4j-graphrag>=0.3.0'
                }

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'execution_time_ms': int((time.time() - start_time) * 1000)
            }

    def _create_llm_adapter(self) -> Optional[Any]:
        """Create LLM adapter for neo4j-graphrag."""
        try:
            import anthropic

            class AnthropicLLMAdapter:
                """Simple adapter for Anthropic Claude with neo4j-graphrag."""

                def __init__(self, api_key: str):
                    self.client = anthropic.Anthropic(api_key=api_key)

                def invoke(self, prompt: str) -> str:
                    """Required method for neo4j-graphrag LLMInterface."""
                    message = self.client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=2000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return message.content[0].text

            return AnthropicLLMAdapter(self.entity_extractor.anthropic_api_key)

        except Exception:
            return None

    def _format_answer(self, result: Any, question: str) -> str:
        """
        Format retriever results into natural language answer.

        Args:
            result: Result from Text2CypherRetriever
            question: Original question

        Returns:
            Natural language answer string
        """
        try:
            # Extract items from result
            items = []
            if hasattr(result, 'items'):
                items = result.items
            elif hasattr(result, 'records'):
                items = result.records
            elif isinstance(result, list):
                items = result

            if not items:
                return "No results found for your query."

            # Count results
            count = len(items)

            # Format based on count
            if count == 0:
                return "No results found."
            elif count == 1:
                return f"Found 1 result: {self._format_item(items[0])}"
            elif count <= 5:
                formatted_items = [self._format_item(item) for item in items]
                return f"Found {count} results:\n" + "\n".join(f"- {item}" for item in formatted_items)
            else:
                formatted_items = [self._format_item(item) for item in items[:5]]
                return (f"Found {count} results (showing first 5):\n" +
                        "\n".join(f"- {item}" for item in formatted_items))

        except Exception as e:
            # Fallback to simple representation
            return f"Query completed. Results: {result}"

    def _format_item(self, item: Any) -> str:
        """Format a single result item."""
        try:
            if isinstance(item, dict):
                # Extract key fields
                if 'name' in item:
                    return item['name']
                elif 'id' in item:
                    return f"ID: {item['id']}"
                else:
                    # Show first few fields
                    fields = list(item.items())[:3]
                    return ", ".join(f"{k}: {v}" for k, v in fields)
            else:
                return str(item)
        except Exception:
            return str(item)
