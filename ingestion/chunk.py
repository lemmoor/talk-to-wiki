import json
import logging
import os
from typing import TypedDict
from semantic_text_splitter import MarkdownSplitter
from urllib.parse import quote
from openai import OpenAI
from dotenv import load_dotenv
import psycopg


load_dotenv()


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class EmbeddingRow(TypedDict):
    wiki_page_id: int
    title: str
    source_url: str
    text: str
    chunk_index: int
    embedding: str  # vector literal, e.g. "[0.1, 0.2, ...]"


def insert_embeddings(rows: list[EmbeddingRow]):
    try:
        with db_conn.cursor() as cur:
            cur.executemany(
                """
                insert into wiki_pages
                    (wiki_page_id, title, source_url, text, chunk_index, embedding)
                values
                    (%(wiki_page_id)s, %(title)s, %(source_url)s, %(text)s, %(chunk_index)s, %(embedding)s::vector)
                """,
                rows,
            )
        db_conn.commit()
        logger.info(f"Inserted {len(rows)} rows into Postgres")
    except Exception as exception:
        db_conn.rollback()
        logger.error(f"Error inserting rows: {exception}")
        raise


splitter = MarkdownSplitter.from_tiktoken_model(
    "text-embedding-3-small", capacity=(150, 500)
)

files = os.listdir("data/pages_md")
openai_client = OpenAI()

db_conn = psycopg.connect(os.environ["DATABASE_URL"])
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
                    "embedding": str(chunk.embedding),
                }
            )

        insert_embeddings(insert_rows)
    except Exception as e:
        logger.error(f"Error processing page {title} ({wiki_page_id}): {e}")
        with open("data/chunk_info.txt", "a") as f:
            f.write(f"{wiki_page_id} {title} Error: {e}\n")
        continue

    page_count += 1
