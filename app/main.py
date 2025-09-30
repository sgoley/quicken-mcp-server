"""Main entry point for the QIF-to-MCP server."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import duckdb

from .config import parse_args
from .qif_loader import load_qif_to_duckdb
from .server import QuickenMCPServer


def setup_logging(log_level: str):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )


def validate_qif_file(qif_path: str) -> bool:
    """Validate QIF file exists and is reasonable size."""
    path = Path(qif_path)

    if not path.exists():
        logging.error(f"QIF file does not exist: {qif_path}")
        return False

    if not path.is_file():
        logging.error(f"QIF path is not a file: {qif_path}")
        return False

    # Check file size (warn if > 100MB)
    file_size = path.stat().st_size
    if file_size > 100 * 1024 * 1024:
        logging.warning(f"Large QIF file detected: {file_size / (1024*1024):.1f}MB")

    if file_size == 0:
        logging.error("QIF file is empty")
        return False

    return True


def setup_duckdb(memory_limit: str):
    """Set up DuckDB connection with configuration."""
    logging.info("Initializing in-memory DuckDB database")

    # Connect to in-memory database
    conn = duckdb.connect(database=':memory:')

    # Configure memory limit
    conn.execute(f"PRAGMA memory_limit='{memory_limit}'")

    # Enable progress bar for long operations
    conn.execute("PRAGMA enable_progress_bar")

    # Optimize for analytics workload
    conn.execute("PRAGMA threads=4")

    return conn


async def main():
    """Main application entry point."""
    try:
        # Parse configuration
        config = parse_args()

        # Setup logging
        setup_logging(config.log_level)
        logger = logging.getLogger(__name__)

        logger.info("Starting QIF-to-MCP server")
        logger.info(f"QIF file: {config.qif_path}")
        logger.info(f"Server mode: {config.server_mode}")
        logger.info(f"Memory limit: {config.memory_limit}")

        # Validate QIF file
        if not validate_qif_file(config.qif_path):
            sys.exit(1)

        # Setup DuckDB
        db_conn = setup_duckdb(config.memory_limit)

        # Load QIF data
        logger.info("Loading QIF data into database...")
        try:
            load_stats = load_qif_to_duckdb(config.qif_path, db_conn)
            logger.info(f"Successfully loaded: {load_stats['accounts']} accounts, "
                       f"{load_stats['categories']} categories, {load_stats['transactions']} transactions")
        except Exception as e:
            logger.error(f"Failed to load QIF data: {e}")
            sys.exit(1)

        # Create and start MCP server
        mcp_server = QuickenMCPServer(db_conn)

        if config.server_mode == "stdio":
            logger.info("Starting MCP server in stdio mode")
            await mcp_server.serve_stdio()

        elif config.server_mode == "sse":
            logger.info(f"Starting MCP server in SSE mode on {config.listen_host}:{config.listen_port}")
            await mcp_server.serve_sse(config.listen_host, config.listen_port)

        else:
            logger.error(f"Unknown server mode: {config.server_mode}")
            sys.exit(1)

    except KeyboardInterrupt:
        logging.info("Server stopped by user")

    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Clean up database connection
        try:
            if 'db_conn' in locals():
                db_conn.close()
                logging.info("Database connection closed")
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())