# pydanticai/search-agent.py
import os
import asyncio
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.agent import RunContext
from fastapi import FastAPI, HTTPException
import uvicorn

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)

# --- Agent Setup (Keep as is) ---

# Define a simple dictionary for capital cities (replace with a real API/DB in practice)
capital_cities_db = {
    "france": "Paris",
    "germany": "Berlin",
    "spain": "Madrid",
    "italy": "Rome",
    "united kingdom": "London",
    "japan": "Tokyo",
    "canada": "Ottawa",
    "australia": "Canberra",
}

# Instantiate the Agent
agent = Agent(
    model="gemini-2.5-pro-preview-03-25",
    system_prompt="You are a helpful web search agent that searches the web to find useful information."
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
    else:
        uvicorn.run(app, host="127.0.0.1", port=8000)