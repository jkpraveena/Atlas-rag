#!/usr/bin/env python3
"""Fetches a real internal-docs-style corpus: ~20 pages from FastAPI's
official tutorial documentation (a real, live, well-structured technical
docs site), pinned to a specific tag for reproducibility, with code-sample
include directives (`{!path/to/file.py!}`) resolved and inlined so the
corpus is fully self-contained -- FastAPI's docs source keeps runnable code
in separate files and includes them at build time, so the raw markdown
alone is incomplete without this step.

DATA PROVENANCE: every file here is real FastAPI documentation, fetched
live from github.com/fastapi/fastapi at tag 0.104.1, not synthetic text.
Re-run this script to refresh the corpus or point SOURCE_TAG at a newer
release.

Usage: python scripts/fetch_docs.py
"""
import re
import sys
import time
from pathlib import Path

import requests

REPO = "fastapi/fastapi"
SOURCE_TAG = "0.104.1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{SOURCE_TAG}"

# repo-relative paths under docs/en/docs/
DOC_PAGES = [
    "index.md",
    "tutorial/index.md",
    "tutorial/first-steps.md",
    "tutorial/path-params.md",
    "tutorial/query-params.md",
    "tutorial/body.md",
    "tutorial/query-params-str-validations.md",
    "tutorial/path-params-numeric-validations.md",
    "tutorial/body-multiple-params.md",
    "tutorial/body-fields.md",
    "tutorial/extra-data-types.md",
    "tutorial/cookie-params.md",
    "tutorial/header-params.md",
    "tutorial/response-model.md",
    "tutorial/extra-models.md",
    "tutorial/response-status-code.md",
    "tutorial/form-data.md",
    "tutorial/request-files.md",
    "tutorial/handling-errors.md",
    "tutorial/path-operation-configuration.md",
    "tutorial/background-tasks.md",
    "tutorial/middleware.md",
    "tutorial/cors.md",
    "tutorial/dependencies/index.md",
    "tutorial/security/index.md",
    "tutorial/security/first-steps.md",
    "tutorial/sql-databases.md",
    "tutorial/bigger-applications.md",
    "tutorial/testing.md",
]

INCLUDE_PATTERN = re.compile(r"\{!\s*([^!]+?)\s*!\}")
HTML_NOISE_PATTERN = re.compile(r"</?(div|span)[^>]*>", re.IGNORECASE)


def resolve_include_path(md_repo_path: str, include_path: str) -> str:
    """Empirically verified against the live repo (not assumed from the
    leading '../' count): every include in this docs tree resolves relative
    to the repo root regardless of how deeply nested the markdown file is
    (e.g. tutorial/security/first-steps.md, one level deeper than
    tutorial/first-steps.md, still uses the same '../../../' prefix). So:
    strip the '>' dedent-marker mkdocs uses on some includes, strip every
    leading '../', and what's left is already repo-root-relative."""
    include_path = include_path.lstrip(">").strip()
    while include_path.startswith("../"):
        include_path = include_path[3:]
    return include_path


def fetch_text(repo_path: str) -> str:
    url = f"{RAW_BASE}/{repo_path}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.text


def inline_code_includes(markdown: str, md_repo_path: str) -> str:
    # Every include in this docs style already sits inside an existing
    # ```Python ... ``` fence in the source markdown -- confirmed by
    # inspection, not assumed -- so the replacement is the raw code only;
    # wrapping it in another fence produces visibly broken nested fences.
    def replace(match):
        include_path = match.group(1)
        resolved = resolve_include_path(md_repo_path, include_path)
        try:
            return fetch_text(resolved).rstrip()
        except requests.RequestException as exc:
            return f"[code example unavailable: {resolved} ({exc})]"

    return INCLUDE_PATTERN.sub(replace, markdown)


def clean_markdown(markdown: str) -> str:
    text = HTML_NOISE_PATTERN.sub("", markdown)
    text = re.sub(r'\{\s*#[\w-]+\s*\}', "", text)  # mkdocs heading-id syntax, e.g. "{ #first-steps }"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main():
    out_dir = Path(__file__).resolve().parent.parent / "docs_corpus"
    out_dir.mkdir(exist_ok=True)

    manifest_lines = [
        f"# Corpus manifest",
        f"Source: https://github.com/{REPO} at tag `{SOURCE_TAG}`",
        f"Fetched: {len(DOC_PAGES)} pages, code-sample includes resolved and inlined.\n",
    ]

    for i, page in enumerate(DOC_PAGES, 1):
        print(f"[{i}/{len(DOC_PAGES)}] Fetching {page}")
        repo_path = f"docs/en/docs/{page}"
        try:
            raw = fetch_text(repo_path)
        except requests.RequestException as exc:
            print(f"  SKIPPED ({exc})", file=sys.stderr)
            continue

        with_code = inline_code_includes(raw, page)
        cleaned = clean_markdown(with_code)

        out_name = page.replace("/", "__")
        (out_dir / out_name).write_text(cleaned)
        manifest_lines.append(f"- `{out_name}` <- `{repo_path}`")
        time.sleep(0.1)

    (out_dir / "MANIFEST.md").write_text("\n".join(manifest_lines) + "\n")
    print(f"\nWrote {len(DOC_PAGES)} documents to {out_dir}")


if __name__ == "__main__":
    main()
