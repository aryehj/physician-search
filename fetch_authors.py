# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "lxml"]
# ///
"""
Stage 1: Search PubMed for piriformis-related publications and extract
all authors with their affiliations.

Outputs: data/authors.json  (deduplicated author list)
         data/articles.json (full article metadata for provenance)

Usage: uv run fetch_authors.py
"""

import json
import time
from pathlib import Path

import httpx
from lxml import etree

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Cast a wide net: piriformis syndrome plus related terms that would
# appear in relevant clinical literature.
SEARCH_QUERIES = [
    "piriformis syndrome",
    "piriformis muscle injection",
    "piriformis release surgery",
    "deep gluteal syndrome",
    "piriformis botulinum toxin",
    "piriformis sciatica",
    "piriformis entrapment",
    "sciatic nerve piriformis",
    "piriformis MRI diagnosis",
    "piriformis electrophysiology",
    "extraspinal sciatica piriformis",
]

DATA_DIR = Path("data")


def search_pmids(client: httpx.Client, query: str, retmax: int = 200) -> list[str]:
    """Return list of PubMed IDs matching a query."""
    resp = client.get(
        f"{EUTILS_BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_articles_xml(client: httpx.Client, pmids: list[str]) -> str:
    """Fetch full article XML for a batch of PMIDs."""
    resp = client.post(
        f"{EUTILS_BASE}/efetch.fcgi",
        data={
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        },
    )
    resp.raise_for_status()
    return resp.text


def parse_articles(xml_text: str) -> list[dict]:
    """Parse PubMed XML into structured article dicts with author info."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    articles = []

    for article_el in root.findall(".//PubmedArticle"):
        # Article metadata
        medline = article_el.find(".//MedlineCitation")
        pmid_el = medline.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else None

        article_node = medline.find("Article")
        title_el = article_node.find("ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""

        # Journal
        journal_el = article_node.find(".//Journal/Title")
        journal = journal_el.text if journal_el is not None else ""

        # Year
        year = None
        for date_path in [
            ".//Article/Journal/JournalIssue/PubDate/Year",
            ".//DateCompleted/Year",
            ".//DateRevised/Year",
        ]:
            year_el = medline.find(date_path)
            if year_el is not None:
                year = year_el.text
                break

        # Authors
        authors = []
        for author_el in article_node.findall(".//AuthorList/Author"):
            last_el = author_el.find("LastName")
            fore_el = author_el.find("ForeName")
            if last_el is None:
                continue
            last_name = last_el.text or ""
            fore_name = fore_el.text if fore_el is not None else ""

            # Collect all affiliations for this author
            affiliations = []
            for aff_el in author_el.findall(".//AffiliationInfo/Affiliation"):
                if aff_el.text:
                    affiliations.append(aff_el.text.strip())

            authors.append(
                {
                    "last_name": last_name,
                    "fore_name": fore_name,
                    "affiliations": affiliations,
                }
            )

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "authors": authors,
            }
        )

    return articles


def deduplicate_authors(articles: list[dict]) -> list[dict]:
    """
    Build a deduplicated author list across all articles.
    Key by normalized (last_name, first_initial) to merge variants.
    Collect all known affiliations and article PMIDs per author.
    """
    author_map: dict[str, dict] = {}

    for article in articles:
        for author in article["authors"]:
            last = author["last_name"].strip()
            fore = author["fore_name"].strip()
            if not last:
                continue

            # Normalize key: lowercase last name + first initial
            first_initial = fore[0].lower() if fore else ""
            key = f"{last.lower()}|{first_initial}"

            if key not in author_map:
                author_map[key] = {
                    "last_name": last,
                    "fore_name": fore,
                    "affiliations": [],
                    "pmids": [],
                    "article_count": 0,
                }

            entry = author_map[key]
            # Keep the longest fore_name variant (e.g., "Loren M" > "L")
            if len(fore) > len(entry["fore_name"]):
                entry["fore_name"] = fore
                entry["last_name"] = last  # keep casing consistent

            # Collect unique affiliations
            for aff in author["affiliations"]:
                if aff and aff not in entry["affiliations"]:
                    entry["affiliations"].append(aff)

            if article["pmid"] and article["pmid"] not in entry["pmids"]:
                entry["pmids"].append(article["pmid"])
                entry["article_count"] += 1

    # Sort by article count descending, then alphabetically
    authors = sorted(
        author_map.values(),
        key=lambda a: (-a["article_count"], a["last_name"].lower()),
    )
    return authors


def main():
    DATA_DIR.mkdir(exist_ok=True)

    all_pmids: set[str] = set()
    all_articles: list[dict] = []
    seen_pmids: set[str] = set()

    with httpx.Client(timeout=30.0) as client:
        # Phase 1: Collect PMIDs from all search queries
        print("=== Searching PubMed ===")
        for query in SEARCH_QUERIES:
            pmids = search_pmids(client, query)
            new = set(pmids) - all_pmids
            print(f"  '{query}': {len(pmids)} results ({len(new)} new)")
            all_pmids.update(pmids)
            time.sleep(0.4)  # respect NCBI rate limits

        print(f"\nTotal unique PMIDs: {len(all_pmids)}")

        # Phase 2: Fetch article metadata in batches
        print("\n=== Fetching article metadata ===")
        pmid_list = sorted(all_pmids)
        batch_size = 100

        for i in range(0, len(pmid_list), batch_size):
            batch = pmid_list[i : i + batch_size]
            print(f"  Fetching batch {i // batch_size + 1} ({len(batch)} articles)...")
            xml_text = fetch_articles_xml(client, batch)
            articles = parse_articles(xml_text)

            for article in articles:
                if article["pmid"] not in seen_pmids:
                    all_articles.append(article)
                    seen_pmids.add(article["pmid"])

            time.sleep(0.4)

    print(f"\nParsed {len(all_articles)} articles")

    # Phase 3: Deduplicate authors
    print("\n=== Deduplicating authors ===")
    authors = deduplicate_authors(all_articles)
    print(f"Found {len(authors)} unique authors")

    # Count US-affiliated authors (rough heuristic)
    us_authors = [
        a
        for a in authors
        if any(
            any(
                marker in aff
                for marker in ["USA", "United States", ", US", "U.S.A"]
            )
            for aff in a["affiliations"]
        )
    ]
    print(f"  of which ~{len(us_authors)} have US affiliations")

    # Save outputs
    articles_path = DATA_DIR / "articles.json"
    authors_path = DATA_DIR / "authors.json"

    with open(articles_path, "w") as f:
        json.dump(all_articles, f, indent=2)
    print(f"\nSaved article metadata to {articles_path}")

    with open(authors_path, "w") as f:
        json.dump(authors, f, indent=2)
    print(f"Saved deduplicated authors to {authors_path}")

    # Print top authors as a quick summary
    print("\n=== Top 20 authors by publication count ===")
    for a in authors[:20]:
        aff_short = a["affiliations"][0][:70] + "..." if a["affiliations"] else "no affiliation"
        print(f"  {a['fore_name']} {a['last_name']} ({a['article_count']} pubs) — {aff_short}")


if __name__ == "__main__":
    main()
