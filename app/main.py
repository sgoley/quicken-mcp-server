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

    # NOTE: `PRAGMA enable_progress_bar` is intentionally NOT enabled. It spawns a
    # native renderer thread that (a) triggers a fatal GIL crash with recent DuckDB
    # builds and (b) could write to stdout and corrupt the MCP stdio JSON-RPC stream.

    # Optimize for analytics workload
    conn.execute("PRAGMA threads=4")

    return conn


async def _serve(mcp_server, config):
    """Run the MCP server in the requested transport mode (async part only)."""
    if config.server_mode == "stdio":
        logging.getLogger(__name__).info("Starting MCP server in stdio mode")
        await mcp_server.serve_stdio()

    elif config.server_mode == "sse":
        logging.getLogger(__name__).info(
            f"Starting MCP server in SSE mode on {config.listen_host}:{config.listen_port}"
        )
        await mcp_server.serve_sse(config.listen_host, config.listen_port)

    else:
        logging.getLogger(__name__).error(f"Unknown server mode: {config.server_mode}")
        sys.exit(1)


def main():
    """Main application entry point.

    The QIF parse + DuckDB load are BLOCKING and must run synchronously in the
    main thread, BEFORE the asyncio event loop is started. Running the DuckDB
    load inside the event loop deadlocks on Windows' Proactor loop (DuckDB
    releases the GIL during long operations). Only the transport serving is
    async, so we enter asyncio.run() with just that.
    """
    db_conn = None
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

        # Load QIF data (synchronous, main thread — NOT inside the event loop)
        logger.info("Loading QIF data into database...")
        try:
            load_stats = load_qif_to_duckdb(config.qif_path, db_conn)
            logger.info(f"Successfully loaded: {load_stats['accounts']} accounts, "
                       f"{load_stats['categories']} categories, {load_stats['transactions']} transactions")
        except Exception as e:
            logger.error(f"Failed to load QIF data: {e}")
            sys.exit(1)

        # Create the MCP server and serve (only the serving is async)
        mcp_server = QuickenMCPServer(db_conn)
        asyncio.run(_serve(mcp_server, config))

    except KeyboardInterrupt:
        logging.info("Server stopped by user")

    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Clean up database connection
        try:
            if db_conn is not None:
                db_conn.close()
                logging.info("Database connection closed")
        except Exception:
            pass


def main_cli():
    """Synchronous entry point for the console script."""
    main()


if __name__ == "__main__":
    main()