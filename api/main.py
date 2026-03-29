import logging, os
from time import time
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
from openai import OpenAI

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = FastAPI()

openai_client = OpenAI()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase_client = create_client(url, key)  # type: ignore


class AskRequest(BaseModel):
    query: str


@app.post("/ask")
def ask(request: AskRequest):
    query = request.query
    try:
        openai_response = openai_client.embeddings.create(
            input=query, model="text-embedding-3-small"
        )

        supabase_response = supabase_client.rpc(
            "match_chunks",
            {
                "query_embedding": openai_response.data[0].embedding,
                "match_count": 5,
            },
        ).execute()

        if not supabase_response.data:
            logger.error(
                f"No data returned from Supabase for query: {query}. Response: {supabase_response}"
            )
            return {
                "query": query,
                "response": "I couldn't find any relevant information. Sorry :(",
            }

        documents = "\n\n"
        for doc in supabase_response.data:
            documents += f"Source URL: {doc['source_url']}\nTitle: {doc['title']}\nText:\n{doc['text']}\n==================\n"

        prompt = """You are a helpful assistant for answering questions about the game Stardew Valley, based on information from the Stardew Valley Wiki. Use only the following information from the wiki to answer the QUESTION. If you don't know the answer, say you don't know. Don't try to use any information that isn't in the provided DOCUMENTS. Every document has it's source URL provided, cite the url of relevant sources in the answer.

QUESTION: {query}

DOCUMENTS: {documents}

respond to the QUESTION based on the information in the DOCUMENTS"""

        chat_response = openai_client.responses.create(
            model="gpt-5-nano",
            input=prompt.format(query=query, documents=documents),
            reasoning={"effort": "low"},
        )

    except Exception as e:
        logger.error(
            f"Error occurred while fetching OpenAI embedding for query: {query}. Error: {e}"
        )
        return {"query": query, "response": "Something went wrong. Too bad, so sad :("}

    return {"query": query, "response": chat_response.output_text}


@app.get("/health")
def health():
    return {"status": "ok"}
