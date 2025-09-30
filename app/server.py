"""MCP server implementation for Quicken data access."""

import asyncio
import json
import logging
from typing import Any, Dict, Sequence
import sys

import mcp.server.stdio
from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.sse import SseServerTransport
from mcp.server.models import InitializationOptions

from .mcp_tools import QuickenMCPTools

logger = logging.getLogger(__name__)


class QuickenMCPServer:
    """MCP server for exposing Quicken financial data."""

    def __init__(self, db_connection):
        self.server = Server("quicken-mcp-server")
        self.tools = QuickenMCPTools(db_connection)
        self._setup_tools()

    def _setup_tools(self):
        """Set up all MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> list[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="list_accounts",
                    description="List all accounts with their basic information including balances",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="list_transactions",
                    description="List transactions with optional filters by account type, date range, category, or payee",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_type": {
                                "type": "string",
                                "description": "Filter by account type (e.g., 'Bank', 'CCard', 'Port')"
                            },
                            "date_from": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format"
                            },
                            "date_to": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format"
                            },
                            "category": {
                                "type": "string",
                                "description": "Filter by category (partial match)"
                            },
                            "payee": {
                                "type": "string",
                                "description": "Filter by payee name (partial match)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of transactions to return (default: 100)",
                                "default": 100
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="run_sql",
                    description="Execute a SQL query against the financial database (SELECT only for security)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL SELECT query to execute"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="get_summaries",
                    description="Get financial summaries and statistics by different time periods",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "period": {
                                "type": "string",
                                "enum": ["month", "category", "account", "all"],
                                "description": "Type of summary to generate",
                                "default": "month"
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_categories",
                    description="Get all categories with their metadata and classification",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="search_transactions",
                    description="Search transactions by text in payee, memo, or category fields",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "Text to search for in transaction details"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 50)",
                                "default": 50
                            }
                        },
                        "required": ["search_term"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> Sequence[types.TextContent]:
            """Handle tool calls."""
            try:
                if name == "list_accounts":
                    result = self.tools.list_accounts()
                elif name == "list_transactions":
                    result = self.tools.list_transactions(
                        account_type=arguments.get("account_type"),
                        date_from=arguments.get("date_from"),
                        date_to=arguments.get("date_to"),
                        category=arguments.get("category"),
                        payee=arguments.get("payee"),
                        limit=arguments.get("limit", 100)
                    )
                elif name == "run_sql":
                    result = self.tools.run_sql(arguments["query"])
                elif name == "get_summaries":
                    result = self.tools.get_summaries(arguments.get("period", "month"))
                elif name == "get_categories":
                    result = self.tools.get_categories()
                elif name == "search_transactions":
                    result = self.tools.search_transactions(
                        arguments["search_term"],
                        arguments.get("limit", 50)
                    )
                else:
                    raise ValueError(f"Unknown tool: {name}")

                # Return the result as JSON
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )
                ]

            except Exception as e:
                logger.error(f"Error calling tool {name}: {e}")
                error_result = {
                    "success": False,
                    "error": str(e),
                    "tool": name,
                    "arguments": arguments
                }
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(error_result, indent=2, default=str)
                    )
                ]

        @self.server.list_resources()
        async def list_resources() -> list[types.Resource]:
            """List available resources."""
            return [
                types.Resource(
                    uri="quicken://ledger_summary",
                    name="Ledger Summary",
                    description="A summary of all financial data in CSV format",
                    mimeType="text/csv"
                ),
                types.Resource(
                    uri="quicken://transactions_export",
                    name="Transactions Export",
                    description="All transactions in CSV format",
                    mimeType="text/csv"
                )
            ]

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read a resource."""
            if uri == "quicken://ledger_summary":
                # Generate a CSV summary
                result = self.tools.get_summaries("all")
                if result["success"]:
                    csv_lines = ["Category,Transaction Count,Total Amount,Average Amount"]
                    for category in result["summaries"].get("categories", []):
                        csv_lines.append(f"{category['category']},{category['transaction_count']},{category['total_amount']},{category['avg_amount']}")
                    return "\n".join(csv_lines)
                else:
                    return "Error generating summary"

            elif uri == "quicken://transactions_export":
                # Export all transactions as CSV
                result = self.tools.run_sql("SELECT date, payee, amount, category, memo FROM transactions ORDER BY date DESC")
                if result["success"]:
                    csv_lines = ["Date,Payee,Amount,Category,Memo"]
                    for row in result["rows"]:
                        # Escape commas in text fields
                        payee = str(row.get("payee", "")).replace(",", ";")
                        category = str(row.get("category", "")).replace(",", ";")
                        memo = str(row.get("memo", "")).replace(",", ";")
                        csv_lines.append(f"{row.get('date','')},{payee},{row.get('amount','')},{category},{memo}")
                    return "\n".join(csv_lines)
                else:
                    return "Error exporting transactions"

            else:
                raise ValueError(f"Unknown resource: {uri}")

    async def serve_stdio(self):
        """Serve using stdio transport."""
        logger.info("Starting MCP server with stdio transport")
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="quicken-mcp-server",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )

    async def serve_sse(self, host: str, port: int):
        """Serve using Server-Sent Events transport."""
        logger.info(f"Starting MCP server with SSE transport on {host}:{port}")

        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import Response
        import uvicorn

        async def handle_sse(request):
            transport = SseServerTransport("/messages")

            async def _run_server():
                async with transport.connect_sse(
                    request.url_for("handle_sse"),
                    request.headers.get("authorization")
                ) as streams:
                    await self.server.run(
                        streams[0],
                        streams[1],
                        InitializationOptions(
                            server_name="quicken-mcp-server",
                            server_version="1.0.0",
                            capabilities=self.server.get_capabilities(
                                notification_options=NotificationOptions(),
                                experimental_capabilities={}
                            )
                        )
                    )

            return transport.handle_post_message(request, _run_server)

        async def health_check(request):
            return Response("OK", status_code=200)

        app = Starlette(routes=[
            Route("/sse", handle_sse, methods=["POST"]),
            Route("/health", health_check, methods=["GET"]),
        ])

        config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()