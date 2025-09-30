# Quicken MCP Server

A containerized MCP (Model Context Protocol) server that converts a local export of Quicken in Quicken Interchange Format (QIF) files into a queryable DuckDB database, exposing financial data through standardized MCP tools to LLM Clients.

## Features

- **QIF Import**: Parse and normalize Quicken QIF files into structured database tables
- **In-Memory Database**: Uses DuckDB for fast, SQL-compatible data access
- **MCP Tools**: Exposes financial data through standardized MCP tools including:
  - `list_accounts` - List all accounts with balances
  - `list_transactions` - Query transactions with flexible filtering
  - `run_sql` - Execute safe SQL queries against the data
  - `get_summaries` - Generate financial summaries and statistics
  - `get_categories` - List transaction categories
  - `search_transactions` - Search transactions by text
- **Multiple Transports**: Supports both stdio and Server-Sent Events (SSE) protocols
- **Security**: SQL queries are restricted to SELECT operations only
- **Resources**: Export data as CSV files through MCP resources

## Quick Start

### Using Docker (Recommended)

1. **Build the container:**
   ```bash
   docker build -t quicken-mcp .
   ```

2. **Run with stdio transport (default):**
   ```bash
   docker run --rm \
     -v "/path/to/your/qif:/data:ro" \
     --network host \
     quicken-mcp --qif /data/yourfile.qif
   ```

3. **Run with SSE transport:**
   ```bash
   docker run --rm \
     -v "/path/to/your/qif:/data:ro" \
     --network host \
     quicken-mcp --qif /data/yourfile.qif --server-mode sse --listen 127.0.0.1:8700
   ```

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run locally:**
   ```bash
   python -m app.main --qif /path/to/your/file.qif
   ```

## Usage Examples

### Command Line Options

```bash
python -m app.main --help
```

Required:
- `--qif PATH` - Path to the QIF file to load

Optional:
- `--server-mode {stdio,sse}` - Transport mode (default: stdio)
- `--listen HOST:PORT` - Listen address for SSE mode (default: 127.0.0.1:8700)
- `--log-level {DEBUG,INFO,WARNING,ERROR}` - Log level (default: INFO)
- `--memory-limit SIZE` - DuckDB memory limit (default: 8GB)

### Environment Variables

You can also configure using environment variables:
- `QIF_PATH` - Path to QIF file
- `SERVER_MODE` - Transport mode
- `LOG_LEVEL` - Logging level
- `MEMORY_LIMIT` - Memory limit

### Docker Examples

**Basic usage with bind mount:**
```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  --network host \
  quicken-mcp --qif /data/example-file.qif
```

**SSE mode with custom port:**
```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  -p 8700:8700 \
  quicken-mcp \
  --qif /data/example-file.qif \
  --server-mode sse \
  --listen 0.0.0.0:8700
```

## MCP Tools Reference

### `list_accounts`
Returns all accounts with metadata:
```json
{
  "success": true,
  "accounts": [
    {
      "account_id": 1,
      "name": "Checking Account",
      "type": "Bank",
      "balance": 1234.56
    }
  ]
}
```

### `list_transactions`
Query transactions with optional filters:
```json
{
  "account_type": "Bank",
  "date_from": "2023-01-01",
  "date_to": "2023-12-31",
  "category": "Food",
  "limit": 50
}
```

### `run_sql`
Execute SELECT queries:
```json
{
  "query": "SELECT category, SUM(amount) FROM transactions WHERE date >= '2023-01-01' GROUP BY category ORDER BY SUM(amount) DESC LIMIT 10"
}
```

### `get_summaries`
Generate financial summaries:
```json
{
  "period": "month"  // Options: "month", "category", "account", "all"
}
```

## Database Schema

The server creates the following tables:

- **accounts** - Account information (name, type, balance, etc.)
- **categories** - Transaction categories and metadata
- **transactions** - Individual transactions
- **transaction_splits** - Split transaction details

Plus useful views:
- **transactions_with_categories** - Transactions joined with category info
- **monthly_summaries** - Monthly spending summaries
- **category_summaries** - Category-wise summaries

## MCP Client Integration

### Testing with MCP Inspector

The MCP Inspector is a powerful debugging tool for testing MCP servers. You can use it to explore available tools, test queries, and debug issues.

**Using Docker (Recommended):**
```bash
# Start the inspector (runs on http://localhost:5173)
docker run --rm --network host -p 5173:5173 ghcr.io/modelcontextprotocol/inspector:latest
```

Then connect to your server:
- **Stdio mode**: Use command `docker run --rm -v "/path/to/your/qif:/data:ro" --network host quicken-mcp --qif /data/yourfile.qif`
- **SSE mode**: Use URL `http://127.0.0.1:8700/sse`

**Using npx (Local Development):**
```bash
# For stdio mode
npx @modelcontextprotocol/inspector docker run --rm -v "/path/to/your/qif:/data:ro" --network host quicken-mcp --qif /data/yourfile.qif

# For SSE mode, start the server first, then:
npx @modelcontextprotocol/inspector http://127.0.0.1:8700/sse
```

### With mcpm (MCP Manager)

Create an mcpm profile:
```bash
mcpm profile create quicken-ledger
mcpm profile edit quicken-ledger --add local::quicken-mcp
```

### With MCP-compatible editors

Configure your editor to use this server:
- **Stdio mode**: Point to the docker run command
- **SSE mode**: Use `http://127.0.0.1:8700/sse` endpoint

## Security Considerations

- QIF files should be trusted and local
- SQL execution is restricted to SELECT statements only
- Dangerous SQL keywords are blocked
- Container runs as non-root user
- File access is controlled through bind mounts

## Performance

- Recommended memory limit: 8GB for large datasets
- File size warning at 100MB+
- Query results limited to prevent memory issues
- DuckDB provides excellent analytical performance

## Development

### Project Structure
```
quicken-mcp-server/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── qif_loader.py      # QIF parsing and database loading
│   ├── schema.sql         # Database schema definitions
│   ├── mcp_tools.py       # MCP tool implementations
│   ├── server.py          # MCP server setup
│   └── main.py           # Application entry point
├── tests/
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Running Tests
```bash
pytest
```

### Code Quality
```bash
ruff check .
mypy app/
```

## License

MIT License - see LICENSE file for details.