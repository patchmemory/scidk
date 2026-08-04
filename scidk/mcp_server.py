#!/usr/bin/env python3
"""
SciDK MCP Server - Model Context Protocol server exposing core SciDK tools.

This server provides external AI agents (Claude Desktop, etc.) with access to:
- Neo4j knowledge graph querying
- Schema introspection
- Dataset summarization
- Label profile retrieval

Usage:
    python -m scidk.mcp_server

Or add to Claude Desktop config:
    {
      "mcpServers": {
        "scidk": {
          "command": "python",
          "args": ["-m", "scidk.mcp_server"],
          "env": {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "password"
          }
        }
      }
    }
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
from neo4j import GraphDatabase


class ScidkMcpServer:
    """
    SciDK MCP Server implementation.

    Provides 5 core tools for external AI agents to interact with SciDK.
    """

    def __init__(self):
        """Initialize server with Neo4j connection."""
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

        # Initialize Neo4j driver
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            # Test connection
            self.driver.verify_connectivity()
            print(f"✅ Connected to Neo4j at {self.neo4j_uri}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}", file=sys.stderr)
            sys.exit(1)

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()

    # Delegate tool implementations to mcp_tools module
    async def query_knowledge_graph(self, cypher: str, parameters: Optional[Dict[str, Any]] = None, limit: Optional[int] = 50) -> Dict[str, Any]:
        return mcp_tools.query_knowledge_graph(self.driver, cypher, self.neo4j_database, parameters, limit)

    async def get_schema(self, max_labels: int = 50, max_props_per_label: int = 5) -> Dict[str, Any]:
        return mcp_tools.get_schema(self.driver, self.neo4j_database, max_labels, max_props_per_label)

    async def summarize_dataset(self, label: Optional[str] = None, relationship: Optional[str] = None) -> Dict[str, Any]:
        return mcp_tools.summarize_dataset(self.driver, self.neo4j_database, label, relationship)

    async def get_label_profile(self, label: str) -> Dict[str, Any]:
        return mcp_tools.get_label_profile(
            self.driver, label, self.neo4j_database,
            settings_db_path=self.settings_db_path,
        )

    async def list_labels(self) -> Dict[str, Any]:
        return mcp_tools.list_labels(self.driver, self.neo4j_database)


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
        """List available tools from centralized definitions."""
        return [
            Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                inputSchema=tool_def["inputSchema"]
            )
            for tool_def in mcp_tools.TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> List[TextContent]:
        """Handle tool calls."""
        try:
            if name == "query_knowledge_graph":
                result = await scidk_server.query_knowledge_graph(
                    cypher=arguments.get("cypher"),
                    parameters=arguments.get("parameters"),
                    limit=arguments.get("limit", 50)
                )
            elif name == "get_schema":
                result = await scidk_server.get_schema(
                    max_labels=arguments.get("max_labels", 50),
                    max_props_per_label=arguments.get("max_props_per_label", 5)
                )
            elif name == "summarize_dataset":
                result = await scidk_server.summarize_dataset(
                    label=arguments.get("label"),
                    relationship=arguments.get("relationship")
                )
            elif name == "get_label_profile":
                result = await scidk_server.get_label_profile(
                    label=arguments["label"]
                )
            elif name == "list_labels":
                result = await scidk_server.list_labels()
            else:
                result = {"status": "error", "error": f"Unknown tool: {name}"}

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error": str(e)
                }, indent=2)
            )]

    # Run server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
