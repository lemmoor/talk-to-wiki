import json
import logging
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _cell_text(cell) -> str:
    """Extract text from a cell, returning empty string for image-only cells."""
    # Remove img tags so alt text doesn't pollute
    for img in cell.find_all("img"):
        img.decompose()
    return cell.get_text(separator=" ", strip=True)


def _fill_grid(rows, header_only: bool) -> list[list[str]]:
    """
    Build a 2D grid from a list of <tr> elements, respecting rowspan/colspan.
    If header_only=True, only processes <th> cells.
    """
    grid: list[list[str]] = []
    # active_rowspans: col_index -> (text, remaining_rows)
    active_rowspans: dict[int, tuple[str, int]] = {}

    for row in rows:
        cell_tag = "th" if header_only else ["th", "td"]
        cells = row.find_all(cell_tag)
        if not cells:
            continue

        grid_row: list[str] = []
        col = 0
        cell_iter = iter(cells)
        cell = next(cell_iter, None)

        while (
            cell is not None
            or col in active_rowspans
            or any(c >= col for c in active_rowspans)
        ):
            # Fill in carried-over rowspan values
            if col in active_rowspans:
                text, remaining = active_rowspans[col]
                grid_row.append(text)
                if remaining - 1 == 0:
                    del active_rowspans[col]
                else:
                    active_rowspans[col] = (text, remaining - 1)
                col += 1
                continue

            if cell is None:
                break

            text = _cell_text(cell)
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))

            for i in range(colspan):
                grid_row.append(text)
                if rowspan > 1:
                    active_rowspans[col + i] = (text, rowspan - 1)

            col += colspan
            cell = next(cell_iter, None)

        if grid_row:
            grid.append(grid_row)

    return grid


def flatten_table(table) -> str:
    """
    Convert an HTML table to key:value pair text lines.

    Handles:
    - Multi-level headers (rowspan/colspan in th rows)
    - Simple single-header tables
    - Infobox tables (no th, first column is label)
    """
    # Replace nested tables with their text so the grid algorithm sees scalar cells
    for nested in table.find_all("table"):
        text = nested.get_text(separator=" ", strip=True)
        nested.replace_with(text)

    rows = table.find_all("tr")
    if not rows:
        return ""

    # Separate header rows (contain th) from data rows (contain td)
    header_rows = [r for r in rows if r.find("th") and not r.find("td")]
    data_rows = [r for r in rows if r.find("td")]

    # --- Build column headers ---
    if header_rows:
        # Build a grid of header cells
        header_grid = _fill_grid(header_rows, header_only=True)

        if not header_grid:
            col_headers: list[str] = []
        elif len(header_grid) == 1:
            col_headers = header_grid[0]
        else:
            # Multi-level: combine parent + child headers
            # header_grid[0] has top-level labels (may span multiple cols via colspan)
            # header_grid[1] has sub-labels
            # After grid filling, both rows are the same width — pair them up
            top = header_grid[0]
            sub = header_grid[1] if len(header_grid) > 1 else []
            col_headers = []
            for i, t in enumerate(top):
                s = sub[i] if i < len(sub) else ""
                if s and s != t:
                    col_headers.append(f"{t} ({s})")
                else:
                    col_headers.append(t)
    else:
        col_headers = []

    # --- Build data rows ---
    data_grid = _fill_grid(data_rows, header_only=False)

    if not data_grid:
        return ""

    lines: list[str] = []

    if col_headers:
        # Standard table: pair headers with cell values
        for row in data_grid:
            pairs = []
            for i, cell in enumerate(row):
                if not cell:
                    continue
                header = col_headers[i] if i < len(col_headers) else f"Col{i+1}"
                if not header:
                    continue
                pairs.append(f"{header}: {cell}")
            if pairs:
                lines.append(" | ".join(pairs))
    else:
        # Infobox pattern: first column is key, second is value
        # But also handle full-width header rows (colspan=2) as section labels
        section_label = ""
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue
            colspan = int(cells[0].get("colspan", 1))
            if colspan >= 2 or len(cells) == 1:
                # Full-width cell — treat as section label
                text = _cell_text(cells[0])
                if text:
                    section_label = text
            elif len(cells) >= 2:
                key = _cell_text(cells[0])
                val = _cell_text(cells[1])
                if key and val:
                    key = key.rstrip(":")
                    if section_label:
                        lines.append(f"{section_label} | {key}: {val}")
                    else:
                        lines.append(f"{key}: {val}")

    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Collect only top-level tables (not nested ones — flatten_table handles those internally)
    top_level_tables = [t for t in soup.find_all("table") if not t.find_parent("table")]
    for table in top_level_tables:
        flat = flatten_table(table)
        table.replace_with("\n\n" + flat + "\n\n" if flat else "")

    text = md(str(soup), strip=["img", "a"])
    text = re.sub(r'data-sort-value="[^"]*">?', "", text)
    return text


if __name__ == "__main__":
    os.makedirs("data/pages_md", exist_ok=True)

    html_dir = Path("data/pages_html")
    pages = list(html_dir.glob("*.json"))
    total = len(pages)

    for i, path in enumerate(pages, 1):
        out_path = Path("data/pages_md") / path.name
        if out_path.exists():
            continue

        data = json.loads(path.read_text())
        markdown = html_to_markdown(data["html"])

        out_path.write_text(
            json.dumps(
                {"title": data["title"], "pageid": data["pageid"], "markdown": markdown}
            )
        )

        if i % 100 == 0:
            logger.info(f"Processed {i}/{total} pages")

    logger.info("Done.")
