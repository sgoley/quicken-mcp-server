# Containerized Quicken-to-MCP Plan

This document splits the work into two tracks:
1. **Quicken → DuckDB MCP server in Docker** – load a `.qif` file into an in-memory DuckDB instance and expose it through a Model Context Protocol (MCP) server that clients can attach to.
2. **Self-hosted LLM chat client (Ollama + Qwen)** – run a local model that can call the MCP server without depending on hosted providers.

Use either track independently or run both for an end-to-end local workflow.

---

## Part 1 — Containerized Quicken → DuckDB MCP Server

### Outcomes
- Accept a host-provided path to a Quicken Interchange Format (QIF) file when the container starts.
- Parse the QIF contents, normalize accounts/transactions, and load them into an in-memory DuckDB database.
- Publish the DuckDB-backed tooling through an MCP server so compatible clients (editors, scripts, CLI agents) can query the data.

### High-level architecture
- **Host invocation**: `docker run --rm -v /path/to/qif:/data:ro --network host quicken-mcp --qif /data/input.qif`
  - Bind-mount the read-only QIF file (or parent directory) into the container.
  - Pass `--qif` (or env var) so the entrypoint script knows what to ingest.
- **Container startup**:
  1. Validate QIF presence and size to avoid loading untrusted multi-GB files.
  2. Launch Python (or Rust/Go) bootstrap that converts QIF → DuckDB tables.
  3. Spin up an MCP server (stdio by default; optional SSE/HTTP) that wraps the DuckDB connection.
- **Tool surface**: Provide structured MCP tools such as:
  - `list_accounts` → returns account metadata.
  - `list_transactions(account, date_range, category, limit)` → filters transactions.
  - `run_sql(query)` → executes arbitrary DuckDB SQL (with guardrails, e.g., whitelist `SELECT`).
  - `summaries(period)` → precomputed aggregates for quick reporting.

### Detailed plan
1. **Project scaffolding**
   - Repo layout:
     ```
     quicken-mcp/
       Dockerfile
       pyproject.toml / requirements.txt
       app/
         __init__.py
         config.py          # CLI/env parsing
         qif_loader.py      # QIF → DuckDB tables
         schema.sql         # Optional CREATE TABLE definitions
         mcp_tools.py       # Tool implementations bound to DuckDB
         server.py          # MCP server bootstrap (stdio + SSE adapters)
         main.py            # Entry point wiring everything together
       tests/
         test_qif_loader.py
         test_mcp_tools.py
     ```
   - Decide on Python 3.11 base image (e.g., `python:3.11-slim`) for easier DuckDB + MCP libraries.
   - Add `ruff`/`pytest` config if you plan to lint or test inside CI.

2. **QIF ingestion module (`qif_loader.py`)**
   - Use `qifparse` or `ofxparse` to read QIF; fall back to manual parsing if library coverage is insufficient.
   - Normalize data into pandas DataFrame(s) or direct DuckDB insertion statements.
   - Suggested tables:
     - `accounts(account_id, name, type, description)`
     - `transactions(tx_id, account_id, date, payee, memo, category, amount)`
     - `categories(category_id, name, parent_category)`
     - `splits(tx_id, split_index, category_id, amount, memo)` (optional).
   - Ensure timezone-agnostic date handling and consistent decimal precision (use `decimal.Decimal` before insert).
   - Validate row counts, duplicate transaction detection, and log ingestion stats.

3. **DuckDB layer (`schema.sql`, `main.py`)**
   - Connect with `duckdb.connect(database=':memory:')` to keep data ephemeral.
   - Apply schema DDL; leverage DuckDB `register()` if staging via DataFrames.
   - Create convenience views (e.g., `transactions_with_categories`) to simplify MCP tool SQL.
   - Optionally persist a temporary `.duckdb` file if you want to snapshot state for debugging.

4. **MCP server surface (`mcp_tools.py`, `server.py`)**
   - Install the official `modelcontextprotocol` Python package (`pip install mcp[server] duckdb qifparse`).
   - Implement tools using `@tool` decorators (stdio server) or by constructing `LspServer`/`SseServer` instances.
   - Map each tool to parameter schemas; enforce limits (e.g., max rows, sanitized SQL) before executing against DuckDB.
   - Provide `resources` (e.g., expose a virtual `ledger_summary.csv`) if clients want downloadable artifacts.
   - Expose metrics/logging to stdout so host can tail container logs for troubleshooting.

5. **Runtime interface & entrypoint (`main.py`)**
   - Parse CLI args (`argparse`) or env vars to obtain `qif_path`, `server_mode` (`stdio` vs `sse`), and optional `--listen :8000` for SSE.
   - Ensure ingestion completes before advertising MCP readiness (use health probe on `/healthz` if running SSE).
   - On shutdown signals (SIGTERM), close DuckDB connection gracefully.

6. **Containerization (`Dockerfile`)**
   - Multi-stage build:
     1. Builder installs dependencies (pip install, compile if needed).
     2. Final slim image copies site-packages + app code.
   - Create non-root user, set `WORKDIR /app`, copy sources.
   - Entrypoint: `ENTRYPOINT ["python", "-m", "app.main"]`.
   - Provide runtime docs for common invocations:
     ```bash
     docker build -t quicken-mcp .
     docker run --rm \
       -v "$PWD/data":/data:ro \
       --network host \
       quicken-mcp --qif /data/2023.qif --server-mode sse --listen 127.0.0.1:8700
     ```

7. **Integration with MCP clients**
   - For stdio: wrap container via `mcpm install local::quicken-mcp` with a recipe that executes `docker run ...`.
   - For SSE/HTTP: document endpoint (`http://127.0.0.1:8700/sse`) and register with clients that support SSE transports.
   - Provide `mcpm profile add quicken-ledger` instructions so other MCP-aware tools can connect.

8. **Testing & validation**
   - Unit tests: mock small QIF files covering deposits, splits, transfers.
   - Integration test: run container locally (`pytest -m integration` or `docker compose run sut`) to ensure tools respond with valid MCP JSON.
   - Performance: benchmark load time for large ledgers; publish guidance on memory caps (DuckDB `PRAGMA memory_limit='8GB'`).
   - Security: reject path traversal (`../../`) arguments, sanitize SQL, and document trust boundary (QIF files should be local and trusted).

### Deliverables checklist
- [ ] Docker image build instructions and sample `docker run` commands.
- [ ] QIF ingestion module with automated tests.
- [ ] MCP tool definitions (stdio + optional SSE) documented with example payloads.
- [ ] `mcpm` recipe or client registration instructions.
- [ ] Observability plan (structured logs, optional `/metrics`).

---

## Part 2 — Local LLM Chat Client (Ollama + Qwen) with MCP Access

### Outcomes
- Run a self-hosted Qwen model through Ollama on macOS/Linux.
- Connect the model to MCP tools (including the Quicken DuckDB server) without relying on hosted LLM APIs.
- Provide a repeatable workflow for both CLI experiments and editor integrations.

### Architecture overview
- **LLM runtime**: Ollama manages model lifecycle and exposes an OpenAI-compatible HTTP API on `http://127.0.0.1:11434`.
- **Orchestrator**: a thin controller that forwards user prompts to Ollama, handles MCP tool calls, and streams responses back to the user.
  - Options: existing MCP-aware clients that support custom OpenAI endpoints (e.g., Cursor, Windsurf, VS Code Cline with `OLLAMA_HOST`), or a bespoke CLI using the `modelcontextprotocol` Python client.
- **Tool plane**: the Dockerized Quicken MCP server (from Part 1) plus any other servers managed by `mcpm`.

### Detailed plan
1. **Host prerequisites**
   - Install Ollama (`brew install ollama` on macOS or official packages on Linux).
   - Ensure hardware can serve the desired Qwen variant (e.g., ≥32 GB RAM for `qwen2.5-coder:14b`, ≥64 GB for `qwen3:32b`).
   - Install `mcpm` if you plan to reuse its profile management (`brew install mcpm`).

2. **Provision the model**
   - Pull the target model: `ollama pull qwen2.5-coder:14b` (swap tags as needed).
   - Test inference: `ollama run qwen2.5-coder:14b "Summarize today's ledger activity."`
   - Optional: configure GPU acceleration (`OLLAMA_NUM_GPU=1`) or offload settings for performance.

3. **Bridge Ollama to MCP-aware clients**
   - **Option A — Editor integrations**
     - Cursor, Windsurf, and VS Code Cline can speak MCP and let you override the OpenAI endpoint.
     - Configure environment variables:
       ```bash
       export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
       export OPENAI_API_KEY=ollama  # dummy token expected by clients
       ```
     - Register the Quicken MCP server via `mcpm profile` or the client’s MCP settings (point to the container’s stdio/SSE endpoint).
   - **Option B — Custom CLI orchestrator**
     - Build a Python script (`ollama_mcp_chat.py`) that:
       1. Uses `httpx` or `ollama` Python SDK to call `POST /api/chat`.
       2. Translates tool requests from the model into MCP invocations using `modelcontextprotocol.client`.
       3. Streams tool responses back into the chat loop and continues until the model finalizes.
     - Maintain conversation state (messages, tool results) in memory; persist transcripts optionally.
     - Provide CLI arguments to select MCP profiles, set temperature, and choose model tags.

4. **Register MCP servers**
   - Use `mcpm profile create ledger-stack` and `mcpm profile edit ledger-stack --add local::quicken-mcp` (plus any other tools).
   - For stdio servers, run via `mcpm profile run`; for SSE servers, ensure the client knows the base URL.
   - Validate connectivity with `mcpm inspect` or the `mcp` inspector web UI.

5. **Conversation flow validation**
   - Scenario tests:
     - Ask the model for “Top 5 expenses last month” → expect a tool call to `run_sql` and a synthesized explanation.
     - Request CSV export → ensure the MCP resource streaming works and the orchestrator saves/returns the file.
   - Evaluate prompt templates that encourage the model to call tools (e.g., system message enumerating available MCP tools and naming conventions).
   - Tune temperature/num_ctx so long ledger summaries remain coherent.

6. **Operational considerations**
   - **Performance**: large Qwen models may require `--num-ctx 8192` to process detailed tool outputs; adjust Ollama `-c` configuration accordingly.
   - **Caching**: optionally run `ollama serve` behind a `litellm` proxy to reuse completions or add rate limiting.
   - **Monitoring**: tail `~/Library/Logs/Ollama/ollama.log` (macOS) and container logs; add structured logging to the orchestrator for tool latency.
   - **Security**: limit MCP tool capabilities exposed to the model; avoid enabling destructive DuckDB SQL (e.g., `DROP TABLE`).

### Deliverables checklist
- [ ] Ollama installation + model pull instructions verified on target host.
- [ ] Client configuration documentation (environment variables, editor-specific steps, or CLI script setup).
- [ ] MCP profile definition referencing the Quicken container.
- [ ] Chat orchestration script or configuration capable of executing MCP tool calls end-to-end.
- [ ] Testing scenarios demonstrating successful tool usage (SQL query, summary generation, export).

---

## Next steps
- Prototype the ingestion script with a small QIF sample to validate schema choices before containerization.
- Decide which MCP transport (stdio vs SSE) your preferred client supports, then finalize the container entrypoint accordingly.
- Draft the custom chat orchestrator only if existing MCP-aware clients cannot use your Ollama endpoint; otherwise document configuration for the supported client.
- Once both tracks work independently, create a combined walkthrough (start container → launch MCP profile → chat via Qwen) for future automation.
