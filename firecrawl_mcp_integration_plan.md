# Software Design Plan: Integrating Firecrawl MCP via Pydantic AI Client

## 1. Introduction

This document outlines the plan to integrate the Firecrawl MCP server as a tool within the `agents/search-agent/search-agent.py` application. The integration will leverage the `pydantic-ai` library's built-in MCP client capabilities, specifically targeting stdio-based MCP servers as documented [1]. This approach replaces direct HTTP request implementations with a standardized client managed by `pydantic-ai`.

## 2. Goals

*   Integrate the Firecrawl MCP server [2] as a tool accessible to the Pydantic AI agent.
*   Utilize the `pydantic-ai` library's `MCPClient` and `MCPStdioServer` for managing the Firecrawl server process via standard input/output.
*   Define a clear process for invoking the `firecrawl_scrape` tool through the MCP client within the agent's tool definition.
*   Ensure the plan accounts for necessary dependencies and configuration adjustments.

## 3. Integration Steps

### 3.1. Dependency Management
1.  **Update Dependencies:** Add `pydantic-ai[mcp]` to the project's requirements file (e.g., `requirements.txt`).
2.  **Install:** Use `uv pip install -r requirements.txt` (or equivalent) to install the necessary MCP client components.

### 3.2. MCP Client Configuration
1.  **Import:** Import `MCPClient` and `MCPStdioServer` from `pydantic_ai.mcp`.
2.  **Define Server Command:** Determine the correct command to launch the Firecrawl MCP server (e.g., `cmd /c npx -y firecrawl-mcp` on Windows, or `npx -y firecrawl-mcp` on Linux/macOS).
3.  **Configure `MCPStdioServer`:** Create an instance of `MCPStdioServer`, providing:
    *   `server_name`: A unique identifier (e.g., `"firecrawl"`).
    *   `command`: The list of strings representing the server startup command.
4.  **Instantiate `MCPClient`:** Create an instance of `MCPClient`, passing a list containing the configured `MCPStdioServer` instance.

### 3.3. Agent Integration
1.  **Modify Agent Initialization:** Pass the created `mcp_client` instance to the `Agent` constructor using the `mcp_client` parameter.

### 3.4. Tool Definition
1.  **Define Tool Function:** Create or modify the Python function that will serve as the agent's tool (e.g., `scrape_website`). Decorate it with `@agent.tool`.
2.  **Function Signature:** Ensure the function accepts `context: RunContext` as its first argument, followed by parameters matching the `firecrawl_scrape` tool's arguments (e.g., `url: str`, `only_main_content: bool = False`).
3.  **Implement Tool Logic:**
    *   Inside the function, access the MCP client via `context.mcp_client`.
    *   Call `context.mcp_client.use_tool()` (or `await context.mcp_client.use_tool()` if defined as async).
    *   Provide the `server_name` (e.g., `"firecrawl"`), `tool_name` (`"firecrawl_scrape"`), and a dictionary of `arguments` matching the Firecrawl tool's schema.
    *   Set an appropriate `timeout` value for the `use_tool` call.
    *   Process the result returned by `use_tool`, extracting the necessary data (e.g., the scraped markdown content).
    *   Implement robust error handling for potential exceptions from the MCP client (e.g., `MCPError`, `ToolNotFoundError`, `TimeoutError`).

### 3.5. Environment and Execution
1.  **Prerequisites:** Ensure the environment where the agent runs has the necessary prerequisites to execute the Firecrawl MCP server command (e.g., Node.js and npx installed).
2.  **Execution:** When the agent application starts, the `MCPClient` will automatically attempt to launch and manage the Firecrawl MCP server subprocess using the configured command.

## 4. References

[1] Pydantic AI - MCP Client Documentation (Stdio Server) (https://ai.pydantic.dev/mcp/client/#mcp-stdio-server)

[2] Firecrawl MCP Server Repository (https://github.com/mendableai/firecrawl-mcp-server)