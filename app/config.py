"""Configuration management for the QIF-to-MCP server."""

import argparse
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration settings for the application."""
    qif_path: str
    server_mode: str = "stdio"  # "stdio" or "sse"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8700
    log_level: str = "INFO"
    memory_limit: str = "8GB"


def parse_args() -> Config:
    """Parse command line arguments and environment variables."""
    parser = argparse.ArgumentParser(
        description="QIF to MCP Server - Convert Quicken files to MCP-accessible database"
    )

    parser.add_argument(
        "--qif",
        required=True,
        help="Path to the QIF file to load"
    )

    parser.add_argument(
        "--server-mode",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP server transport mode (default: stdio)"
    )

    parser.add_argument(
        "--listen",
        default="127.0.0.1:8700",
        help="Host:port to listen on for SSE mode (default: 127.0.0.1:8700)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )

    parser.add_argument(
        "--memory-limit",
        default="8GB",
        help="DuckDB memory limit (default: 8GB)"
    )

    args = parser.parse_args()

    # Parse listen address
    if ":" in args.listen:
        host, port_str = args.listen.rsplit(":", 1)
        port = int(port_str)
    else:
        host = args.listen
        port = 8700

    # Check for environment variable overrides
    qif_path = os.getenv("QIF_PATH", args.qif)
    server_mode = os.getenv("SERVER_MODE", args.server_mode)
    log_level = os.getenv("LOG_LEVEL", args.log_level)
    memory_limit = os.getenv("MEMORY_LIMIT", args.memory_limit)

    return Config(
        qif_path=qif_path,
        server_mode=server_mode,
        listen_host=host,
        listen_port=port,
        log_level=log_level,
        memory_limit=memory_limit
    )