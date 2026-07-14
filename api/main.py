import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logfire
from pydantic import BaseModel, Field
from typing import List
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from openai import OpenAI

load_dotenv()


app = FastAPI()

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

logfire.configure()
logfire.instrument_fastapi(app)

openai_client = OpenAI()
logfire.instrument_openai(openai_client)

db_pool = ConnectionPool(
    conninfo=os.environ.get("DATABASE_URL", ""),
    min_size=0,
    max_size=5,
    kwargs={"row_factory": dict_row},
    open=True,
)


class AskRequest(BaseModel):
    query: str


class Source(BaseModel):
    url: str = Field(description="The URL of the source used to generate the answer")
    title: str = Field(description="The title of the source")


class RequestAnswer(BaseModel):
    answer: str = Field(
        description="The answer to the user's questions, based on the provided documents. The user does not see or know of the documents."
    )
    sources: List[Source] = Field(
        description="List of sources and titles used to generate the answer."
    )


@app.post("/ask")
def ask(request: AskRequest):
    query = request.query
    try:
        openai_response = openai_client.embeddings.create(
            input=query, model="text-embedding-3-small"
        )

        with db_pool.connection() as conn:
            matched_chunks = conn.execute(
                """
                with top_chunks as (
                    select title, source_url, chunk_index,
                           1 - (embedding <=> %(query_embedding)s::vector) as similarity
                    from wiki_pages
                    order by embedding <=> %(query_embedding)s::vector
                    limit 5
                )
                select
                    tc.title,
                    string_agg(neighbor.text, ' ' order by neighbor.chunk_index) as text,
                    tc.source_url
                from top_chunks tc
                join wiki_pages neighbor
                  on neighbor.title = tc.title
                 and neighbor.chunk_index between tc.chunk_index - 1 and tc.chunk_index + 1
                group by tc.title, tc.source_url, tc.chunk_index, tc.similarity
                order by tc.similarity desc
                """,
                {"query_embedding": str(openai_response.data[0].embedding)},
            ).fetchall()

        if not matched_chunks:
            raise HTTPException(
                status_code=404, detail="No relevant information found."
            )

        documents = "\n\n"
        for doc in matched_chunks:
            documents += f"Source URL: {doc['source_url']}\nTitle: {doc['title']}\nText:\n{doc['text']}\n==================\n"

        prompt = """You are a helpful assistant for answering questions about the game Stardew Valley, based on information from the Stardew Valley Wiki. Use only the following information from the wiki to answer the QUESTION. If you don't know the answer, say you don't know. Don't try to use any information that isn't in the provided DOCUMENTS. Cite the sources in the relevant json field, never in the answer text itself.
Some documents contain data from wiki tables that were flattened from multi-row, multi-header tables. Headers or values may appear repeated or out of order — use context to interpret them correctly.
Try to give as much information as you can, with useful tip and tricks or recommendations following from the documents.

QUESTION: {query}

DOCUMENTS: {documents}

respond to the QUESTION based on the information in the DOCUMENTS"""

        chat_response = openai_client.responses.parse(
            model="gpt-5-nano",
            input=prompt.format(query=query, documents=documents),
            reasoning={"effort": "low"},
            text_format=RequestAnswer,
        )

    except Exception as e:
        logfire.error("Error processing query: {query}", query=query, _exc_info=e)
        raise HTTPException(status_code=500, detail="Something went wrong.")

    if not chat_response.output_parsed:
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")

    return {"query": query, "response": chat_response.output_parsed}


@app.get("/health")
def health():
    return {"status": "ok"}
