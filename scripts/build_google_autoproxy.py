#!/usr/bin/env python3
"""Convert V2Fly domain-list-community's Google category to AutoProxy."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

BASE_URL = "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/"
OUTPUT = Path("google-autoproxy.txt")
visited: set[str] = set()
domain_rules: set[str] = set()
exact_rules: set[str] = set()
unsupported: set[str] = set()


def fetch(category: str) -> str:
    with urlopen(BASE_URL + category, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def valid_domain(value: str) -> bool:
    value = value.rstrip(".").lower()
    if not value or len(value) > 253 or "." not in value:
        return False
    labels = value.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in labels
    )


def visit(category: str) -> None:
    category = category.strip()
    if not category or category in visited:
        return
    visited.add(category)

    try:
        source = fetch(category)
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Unable to fetch V2Fly category {category!r}: {exc}") from exc

    for raw_line in source.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        # Attributes (for example @cn or @ads) follow the rule token.
        token = line.split()[0]

        if token.startswith("include:"):
            visit(token.partition(":")[2])
            continue

        if token.startswith("domain:"):
            kind, value = "domain", token.partition(":")[2]
        elif token.startswith("full:"):
            kind, value = "full", token.partition(":")[2]
        elif token.startswith("keyword:"):
            kind, value = "keyword", token.partition(":")[2]
        elif token.startswith("regexp:"):
            kind, value = "regexp", token.partition(":")[2]
        elif ":" not in token:
            # V2Fly explicitly allows a bare domain as shorthand for domain:.
            kind, value = "domain", token
        else:
            unsupported.add(token)
            continue

        value = value.strip().lower().rstrip(".")
        if kind == "domain" and valid_domain(value):
            domain_rules.add(value)
        elif kind == "full" and valid_domain(value):
            exact_rules.add(value)
        elif kind in {"keyword", "regexp"}:
            # AutoProxy cannot faithfully represent arbitrary substring/regex rules.
            unsupported.add(token)
        else:
            unsupported.add(token)


def main() -> int:
    visit("google")

    # Fail safely if an upstream format change or fetch issue causes a tiny list.
    if len(domain_rules) + len(exact_rules) < 100:
        raise RuntimeError(
            f"Only {len(domain_rules) + len(exact_rules)} rules were parsed; "
            "expected at least 100. Refusing to publish an incomplete list."
        )

    lines = [
        "[AutoProxy 0.2.9]",
        "! Title: Google domains (V2Fly domain-list-community)",
        "! Homepage: https://github.com/v2fly/domain-list-community",
        "! Source: https://github.com/v2fly/domain-list-community/blob/master/data/google",
        "! Generated automatically by scripts/build_google_autoproxy.py",
        "",
    ]
    # domain: and bare entries match the domain and all subdomains.
    lines.extend(f"||{domain}^" for domain in sorted(domain_rules))
    # full: matches exactly this hostname, not its subdomains.
    lines.extend(f"|{domain}|" for domain in sorted(exact_rules))
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Visited source categories: {len(visited)}")
    print(f"Domain rules: {len(domain_rules)}")
    print(f"Exact-host rules: {len(exact_rules)}")
    print(f"Skipped unsupported entries: {len(unsupported)}")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    if unsupported:
        print("Some keyword/regexp or unsupported entries were skipped.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
