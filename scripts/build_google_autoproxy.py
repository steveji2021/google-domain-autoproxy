#!/usr/bin/env python3
"""Convert V2Fly domain-list-community's Google category to AutoProxy."""
from __future__ import annotations

import re
import sys
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path

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

        if line.startswith("include:"):
            visit(line.partition(":")[2])
            continue

        kind, sep, value = line.partition(":")
        if not sep:
            # Ignore unknown future syntax rather than guessing its semantics.
            unsupported.add(line)
            continue

        value = value.strip().lower().rstrip(".")
        if kind == "domain" and valid_domain(value):
            domain_rules.add(value)
        elif kind == "full" and valid_domain(value):
            exact_rules.add(value)
        elif kind in {"keyword", "regexp"}:
            # AutoProxy cannot faithfully represent arbitrary substring/regex rules.
            unsupported.add(line)
        else:
            unsupported.add(line)


def main() -> int:
    visit("google")
    if not domain_rules and not exact_rules:
        raise RuntimeError("No valid domain entries were found; refusing to publish an empty list.")

    lines = [
        "[AutoProxy 0.2.9]",
        "! Title: Google domains (V2Fly domain-list-community)",
        "! Homepage: https://github.com/v2fly/domain-list-community",
        "! Source: https://github.com/v2fly/domain-list-community/blob/master/data/google",
        "! Generated automatically by scripts/build_google_autoproxy.py",
        "",
    ]
    # domain: means the domain and all subdomains.
    lines.extend(f"||{domain}^" for domain in sorted(domain_rules))
    # full: means exactly this hostname, not its subdomains.
    lines.extend(f"|{domain}|" for domain in sorted(exact_rules))
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Visited source categories: {len(visited)}")
    print(f"Domain rules: {len(domain_rules)}")
    print(f"Exact-host rules: {len(exact_rules)}")
    print(f"Skipped unsupported entries: {len(unsupported)}")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    if unsupported:
        print("Some source entries use syntax AutoProxy cannot represent; see workflow log.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
