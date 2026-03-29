import json
import logging
import os
from typing import TypedDict
from semantic_text_splitter import MarkdownSplitter
from urllib.parse import quote
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class EmbeddingRow(TypedDict):
    wiki_page_id: int
    title: str
    source_url: str
    text: str
    chunk_index: int
    embedding: list[float]


def insert_embeddings(rows: list[EmbeddingRow]):
    try:
        response = supabase_client.table("wiki_pages").insert(rows).execute()  # type: ignore
        logger.info(f"Inserted {len(rows)} rows into Supabase")
        return response
    except Exception as exception:
        logger.error(f"Error inserting rows: {exception}")
        raise


splitter = MarkdownSplitter.from_tiktoken_model(
    "text-embedding-3-small", capacity=(150, 500)
)

files = os.listdir("data/pages_md")
openai_client = OpenAI()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase_client = create_client(url, key)  # type: ignore
page_count = 0
for file in files:
    with open(f"data/pages_md/{file}", "r") as f:
        page_response = json.load(f)

    chunks = splitter.chunks(page_response["markdown"])
    title = page_response["title"]
    page_url = f"https://stardewvalleywiki.com/{quote(title.replace(' ', '_'))}"
    wiki_page_id = page_response["pageid"]

    if len(chunks) == 0:
        logger.warning(
            f"Page {title} ({wiki_page_id}) has no content after splitting, skipping."
        )
        with open("data/chunk_info.txt", "a") as f:
            f.write(f"{wiki_page_id} {title} No chunks\n")
        continue

    logger.info(
        f"[{page_count+1}/{len(files)}] Page {title} ({wiki_page_id}) split into {len(chunks)} chunks:"
    )
    to_embed = [title + "\n\n" + chunk for chunk in chunks]

    try:
        response = openai_client.embeddings.create(
            input=to_embed, model="text-embedding-3-small"
        )

        insert_rows = []
        for i, chunk in enumerate(response.data):
            logger.debug(f"Chunk {i+1} embedding: {chunk.embedding[:5]}...")
            insert_rows.append(
                {
                    "wiki_page_id": wiki_page_id,
                    "title": title,
                    "source_url": page_url,
                    "text": chunks[i],
                    "chunk_index": i,
                    "embedding": chunk.embedding,
                }
            )

        insert_embeddings(insert_rows)
    except Exception as e:
        logger.error(f"Error processing page {title} ({wiki_page_id}): {e}")
        with open("data/chunk_info.txt", "a") as f:
            f.write(f"{wiki_page_id} {title} Error: {e}\n")
        continue

    page_count += 1
