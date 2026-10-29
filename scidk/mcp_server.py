#!/usr/bin/env python3
"""SciDK MCP adapter over the canonical scoped agent registry.

Stdio has no principal binding and advertises no tools. A trusted host may inject
an authenticated ToolContext; discovery/execution still recheck all policy. No
identity is accepted from environment variables or tool arguments.
"""
import asyncio
import os
import sys
import json
from typing import Any, Dict, List, Optional

# Import MCP SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, Resource
except ImportError:
    print("ERROR: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Add project root to path
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import SciDK modules
from scidk.ai import mcp_tools
from scidk.agent_tools.registry import CHAT_ONLY
from neo4j import GraphDatabase


class ScidkMcpServer:
    """
    SciDK MCP Server implementation.

    Shares the HTTP/chat handlers; never constructs an unscoped graph context.
    """

    def __init__(self, *, tool_context=None):
        """Initialize without graph I/O; stdio remains unbound by default."""
        self.neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
        self.neo4j_database = os.getenv('NEO4J_DATABASE', 'neo4j')

        # Schema Intelligence (label profiles, property rankings) lives in
        # scidk_settings.db. This process has no Flask app to read the path from
        # app.config, so the env var and the cwd default are all there is —
        # meaning the server must be started from the SciDK working directory,
        # or SCIDK_SETTINGS_DB must be set in its MCP config env block.
        self.settings_db_path = os.getenv('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        if not os.path.exists(self.settings_db_path):
            print(
                f"⚠️  Settings DB not found at {self.settings_db_path} — label "
                "profiles and property rankings will be unavailable. Set "
                "SCIDK_SETTINGS_DB to the SciDK settings database to enable them.",
                file=sys.stderr,
            )

        # Stdio has no authenticated principal or approved destination. No graph
        # connection may be attempted for calls which will be refused.
        self.driver = None
        # Only a trusted hosting adapter can inject a verified server binding.
        # Stdio/env/tool arguments never construct identities or capabilities.
        from scidk.agent_tools.registry import ToolContext
        self.tool_context = tool_context if tool_context is not None else ToolContext(settings_db=self.settings_db_path)

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()

    def dispatch(self, name, arguments):
        from scidk.agent_tools.registry import ToolContext, run_tool
        return run_tool(name, arguments, self.tool_context)

    def tool_definitions(self):
        from scidk.agent_tools.registry import available_tool_definitions
        return available_tool_definitions(self.tool_context)

    async def query_knowledge_graph(self, cypher, parameters=None, limit=50):
        return self.dispatch('query_knowledge_graph', dict(cypher=cypher, parameters=parameters, limit=limit))

    async def get_schema(self, max_labels=50, max_props_per_label=5):
        return self.dispatch('get_schema', dict(max_labels=max_labels, max_props_per_label=max_props_per_label))

    async def summarize_dataset(self, label=None, relationship=None):
        return self.dispatch('summarize_dataset', dict(label=label, relationship=relationship))

    async def get_label_profile(self, label):
        return self.dispatch('get_label_profile', dict(label=label))

    async def list_labels(self):
        return self.dispatch('list_labels', {})


# ============================================================================
# MCP Server setup
# ============================================================================

async def main():
    """Main entry point for MCP server."""
    # Create SciDK server instance
    scidk_server = ScidkMcpServer()

    # Create MCP server
    server = Server("scidk")

    # Register tools
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available tools from the canonical registry in mcp_tools.

        `input_schema` is the registry's spelling — snake_case, matching the
        :Concept_Tool node property — and `inputSchema` is MCP's. This is the
        one place the two meet.
        """
        return [
            Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                inputSchema=tool_def["input_schema"]
            )
            for tool_def in scidk_server.tool_definitions()
            if tool_def["name"] not in CHAT_ONLY
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> List[TextContent]:
        """Run a tool through the shared registry, so the result passes the same
        disclosure filter as every other adapter (agent_tools.run_tool)."""
        result = scidk_server.dispatch(name, {} if arguments is None else arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    # Run server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
