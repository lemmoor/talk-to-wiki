import os
import re
import time

import httpx
import json
import logging
from bs4 import BeautifulSoup
from markdownify import markdownify as md

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def fetch_pages():
    r = httpx.get(
        "https://stardewvalleywiki.com/mediawiki/api.php?action=query&list=allpages&aplimit=max&format=json"
    )

    response = r.json()

    pages = response["query"]["allpages"]

    while response.get("continue") and not response.get("batchcomplete"):
        logger.info("Fetching next batch of pages...")
        apcontinue = response["continue"]["apcontinue"]
        r = httpx.get(
            f"https://stardewvalleywiki.com/mediawiki/api.php?action=query&list=allpages&aplimit=max&format=json&apcontinue={apcontinue}"
        )
        response = r.json()
        pages.extend(response["query"]["allpages"])

    with open("data/pages.json", "w") as f:
        json.dump(pages, f)


def fetch_page_content(pageid: int) -> str:
    r = httpx.get(
        f"https://stardewvalleywiki.com/mediawiki/api.php?action=parse&pageid={pageid}&prop=text|categories&format=json",
        timeout=30,
    )
    r.raise_for_status()

    response = r.json()

    return response


with open("data/pages.json", "r") as f:
    pages = json.load(f)

skipped_ids = set()
if os.path.exists("data/skipped.txt"):
    with open("data/skipped.txt", "r") as f:
        for line in f:
            skipped_ids.add(int(line.split()[0]))

for page in pages:
    pageid, ns, title = page["pageid"], page["ns"], page["title"]

    if os.path.exists(f"data/pages_html/{pageid}.json") or pageid in skipped_ids:
        logger.info(f"Skipping page ID {pageid} ({title})")
        continue

    time.sleep(2)  # be nice to wiki :)
    logger.info(f"Processing page ID {pageid} ({title})...")
    page_response = fetch_page_content(pageid)
    print(pageid, ns, title)
    html_string = page_response["parse"]["text"]["*"]

    soup = BeautifulSoup(html_string, "html.parser")

    # Remove common wiki clutter
    for element in soup.select(
        ".mw-editsection, "  # [edit] links next to headers
        ".navbox, "  # navigation boxes at bottom
        "#navbox,"
        ".catlinks, "  # category bar
        ".toc, "  # table of contents
        ".mw-empty-elt, "  # empty placeholder elements
        ".noprint, "  # stuff hidden from print view
        ".sidebar, "  # sidebars
        "#toc, "  # toc by id
        ".mw-references-wrap, "  # reference list (footnotes)
        "sup.reference,"  # inline citation markers [1], [2]
        "dl"  # definition lists with metadata (Main article: Marriage)
    ):
        element.decompose()

    clean_html = str(soup)
    # this was the old processing befor I realised the multilevel tables are a mess when converted in this way. (process.py handles that)
    # markdown = md(clean_html, strip=["img", "a"])
    # markdown = re.sub(r'data-sort-value="[^"]*">?', "", markdown)

    # if markdown.strip().startswith("Redirect to:"):
    #     logger.info(f"Page {title} ({pageid}) is a redirect, skipping.")
    #     with open("data/skipped.txt", "a") as f:
    #         f.write(f"{pageid} {title}\n")
    #     continue

    with open(f"data/pages_html/{pageid}.json", "w") as f:
        json.dump({"title": title, "pageid": pageid, "html": clean_html}, f)
