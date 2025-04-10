# pydanticai/search-agent.py
import os
import asyncio
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.agent import RunContext
from fastapi import FastAPI, HTTPException
import uvicorn
from typing import Any # Added for ScrapeResponse flexibility

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    raise RuntimeError("FIRECRAWL_API_KEY is not set. Please ensure it is present in agents/search-agent/.env before starting the server.")

# --- Agent Setup (Keep as is) ---


# Instantiate the Firecrawl MCP Server
firecrawl_mcp_command_args = ["/c", "npx", "-y", "firecrawl-mcp"]
firecrawl_mcp_env = {"FIRECRAWL_API_KEY": FIRECRAWL_API_KEY} if FIRECRAWL_API_KEY else {}
firecrawl_server = MCPServerStdio(
    command="cmd", # Set command to "cmd"
    args=firecrawl_mcp_command_args,
    env=firecrawl_mcp_env
)

# Instantiate the Agent
agent = Agent(
    model="gemini-2.5-pro-preview-03-25",
    system_prompt="You are a helpful web search agent that searches or scrapes the web to find useful information.",
    instrument=True,
    mcp_servers=[firecrawl_server]
)

# Define the Brave Search tool
@agent.tool
def web_search(context: RunContext, query: str, count: int = 5) -> str:
    """
    Performs a web search using the Brave Search API.

    Args:
        query: The search query string.
        count: The number of results to return (default: 5).

    Returns:
        A formatted string containing the search results (title and URL)
        or an error message.
    """
    print("--- Executing web_search tool ---") # Add log to confirm tool usage
    brave_api_key = os.getenv("BRAVE_API_KEY")
    if not brave_api_key:
        return "Error: BRAVE_API_KEY not found in environment variables."

    search_url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": brave_api_key
    }
    params = {
        "q": query,
        "count": count
    }

    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        data = response.json()
        results = data.get('web', {}).get('results', [])

        if not results:
            return f"No search results found for '{query}'."

        formatted_results = "Search Results:\n"
        for i, result in enumerate(results):
            title = result.get('title', 'No Title')
            url = result.get('url', 'No URL')
            formatted_results += f"{i+1}. {title}\n   {url}\n"

        return formatted_results.strip()

    except requests.exceptions.RequestException as e:
        return f"Error during Brave Search API request: {e}"
    except Exception as e:
        return f"An unexpected error occurred during web search: {e}"

# +++ Add tool definition back +++
@agent.tool
async def scrape_website(context: RunContext, url: str) -> Any:
    """
    Scrapes the content of a given URL using the Firecrawl service. Use this tool
    when asked to scrape or get the content of a specific webpage.

    Args:
        url: The URL of the website to scrape.

    Returns:
        The scraped content (typically markdown) or an error message if scraping fails.
    """
    print(f"--- Executing scrape_website tool for URL: {url} ---")
    try:
        # Ensure MCP servers are running when the tool is invoked by the agent
        # Although agent.run manages servers, explicit check within tool can be safer
        # if tool could be called outside agent.run context (though unlikely here).
        # Let's rely on agent.run's management for now.

        async with agent.run_mcp_servers():
            result = await agent.run(f'scrape this url {url} using firecrawl_scrape tool')
            print(f"Raw result type from MCP tool: {type(result)}") # Log type

        # Extract relevant data from the result
        if isinstance(result, dict):
            if 'markdown' in result:
                print("Markdown content successfully retrieved.")
                return result['markdown'] # Return the markdown content
            elif 'error' in result:
                 error_message = f"Error from firecrawl_scrape: {result['error']}"
                 print(error_message)
                 return error_message # Return error message for the agent
            else:
                 # Log unexpected structure
                 print(f"Unexpected result structure from firecrawl_scrape: {result}")
                 return f"Unexpected response structure from scraping service: {str(result)[:100]}..." # Return error
        else:
            # Log unexpected type
            print(f"Unexpected result type from firecrawl_scrape: {type(result)}")
            return f"Unexpected response type from scraping service: {type(result)}" # Return error

    except Exception as e:
        print(f"Error within scrape_website tool using firecrawl_scrape via MCP: {e}")
        import traceback
        traceback.print_exc()
        # Provide a more informative error message back to the agent
        return f"Error occurred within scrape_website tool while trying to scrape URL '{url}': {e}"
# +++ End tool definition +++

# --- FastAPI Implementation ---

app = FastAPI(
    title="PydanticAI Search Agent API",
    description="API endpoint to interact with the search agent.",
    version="1.0.0"
)

class QueryRequest(BaseModel):
    query: str = Field(..., description="The query to send to the agent.")

class QueryResponse(BaseModel):
    response: str = Field(..., description="The agent's response.")

# +++ Add new models +++
class ScrapeRequest(BaseModel):
    url: str = Field(..., description="The URL to scrape.")

class ScrapeResponse(BaseModel):
    content: Any = Field(..., description="The scraped content from the URL.")
# +++ End new models +++

@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """
    Receives a query, runs it through the PydanticAI agent, and returns the response.
    """
    print(f"\nReceived query: {request.query}")
    print("Thinking...")
    try:
        # Run the agent with the user's query
        result_wrapper = await agent.run(request.query)
        response_data = result_wrapper.data

        print(f"Agent response: {response_data}")
        return QueryResponse(response=response_data)

    except Exception as e:
        print(f"\nAn error occurred processing the query: {e}")
        # Consider more specific error handling based on potential agent errors
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# +++ Add new endpoint +++
@app.post("/scrape", response_model=ScrapeResponse)
async def handle_scrape(request: ScrapeRequest):
    """
    Receives a URL, uses agent.run to instruct the agent to use the
    scrape_website tool, and returns the scraped content.
    """
    print(f"\nReceived scrape request for URL: {request.url}")
    print("Instructing agent to scrape using agent.run...")
    try:
        # Construct the instruction for the agent
        # Make it clear we want the content from the specific URL using the tool
        scrape_instruction = f"Please scrape the content of the website at the URL '{request.url}' using the 'scrape_website' tool and return the raw scraped content."
        print(f"Running agent with instruction: \"{scrape_instruction}\"")

        # Use agent.run - this will manage MCP server lifecycle if the tool is called
        async with agent.run_mcp_servers():
            result_wrapper = await agent.run(scrape_instruction)
        
        scraped_content = result_wrapper.data # Agent returns the output of the tool

        # Log the type and value for debugging
        print(f"Agent run completed. Result type: {type(scraped_content)}")
        # Avoid printing potentially very large scraped content to logs
        content_snippet = str(scraped_content)[:200] + "..." if isinstance(scraped_content, str) else "(Non-string content)"
        print(f"Scraped content snippet: {content_snippet}")

        # Check if the tool execution (via agent) returned an error string
        # (Based on the return values in the scrape_website tool implementation)
        if isinstance(scraped_content, str) and (
            scraped_content.startswith("Error from firecrawl_scrape:") or
            scraped_content.startswith("Error occurred within scrape_website tool") or
            scraped_content.startswith("Unexpected response")
            ):
             print(f"Agent's tool execution resulted in an error: {scraped_content}")
             # Return a 500 error, passing the specific error message from the tool/agent
             raise HTTPException(status_code=500, detail=scraped_content)
        elif scraped_content is None or scraped_content == "":
             # Handle cases where the agent might fail to extract or return content
             print("Agent returned empty or None content after scraping attempt.")
             raise HTTPException(status_code=500, detail="Agent failed to return scraped content.")


        print(f"Scraping successful via agent.run for URL: {request.url}")
        return ScrapeResponse(content=scraped_content)

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions directly
        raise http_exc
    except Exception as e:
        print(f"\nAn error occurred processing the scrape request via agent.run: {e}")
        # Log the full traceback for detailed debugging
        import traceback
        traceback.print_exc()
        # More generic error as agent.run encapsulates tool errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during the agent-driven scraping process: {e}")
# +++ End new endpoint +++

# --- Uvicorn Runner ---

if __name__ == "__main__":
    print("Starting FastAPI server...")
    # Check for API keys before starting server
    google_key = os.getenv("GOOGLE_API_KEY")
    brave_key = os.getenv("BRAVE_API_KEY")
    if not google_key:
        print("ERROR: GOOGLE_API_KEY not found in .env file. Server cannot start.")
    elif not brave_key:
         print("ERROR: BRAVE_API_KEY not found in .env file. Server cannot start.")
    elif not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not found in .env file. Server cannot start.")
    else:
        uvicorn.run(app, host="127.0.0.1", port=8000)
