# Spanish-language news collector

This is a local, bounded collector of Spanish-language agricultural articles with a separate editorial review step. It is **not connected to a cloud news scheduler, Azure news importer or public application feed**. Its records are separate from official price observations.

## Implementation

[sources.json](sources.json) defines candidate origins and source policies. [cli.py](cli.py) orchestrates discovery and collection; [content.py](content.py) handles extraction and classification rules; [state.py](state.py) maintains resumable SQLite state; [transport.py](transport.py) handles bounded requests.

The collector records source URLs, titles, short evidence extracts, publication dates, hashes and review state. It does not archive full article bodies or publisher images. A source's inclusion in the catalog does not establish display rights or complete coverage.

Publication dates must come from article metadata or explicit publisher text. Masthead, event and modification dates do not silently replace them. Ambiguous dates, inaccessible sources and unsupported layouts remain visible as unresolved records.

Automated triage proposes categories; editorial decisions remain a separate input. Facts from an article and inferred implications for Colombia are kept distinct. Canonical URLs and event grouping reduce duplicate stories. Expiry depends on content category and does not mean an underlying risk has ended.

## Local setup

From the repository root, after creating a Python virtual environment:

```sh
.venv/bin/pip install -r pipelines/news/requirements.txt
.venv/bin/python -m pipelines.news.cli catalog
```

The CLI provides collection, review and export commands. Default SQLite state and outputs live in the ignored `pipelines/news/cache/` directory; preserve local state when resuming a collection. No model API call or public publication follows merely from running the collector.

See [pipeline architecture](../README.md) for the separate official-data ingestion path.
