#!/usr/bin/env python3
"""Convert V2Fly domain-list-community's Google category to AutoProxy.

The converter deliberately fails closed when it encounters source syntax that
cannot be represented without guessing. This prevents silently publishing an
incomplete or misleading proxy list.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Union
from urllib.error import URLError
from urllib.request import urlopen

BASE_URL = "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/"
OUTPUT = Path("google-autoproxy.txt")
MIN_RULE_COUNT = 100
DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", re.IGNORECASE)
# A fixed, escaped multi-label suffix at the end of a V2Fly regexp can safely
# be broadened to that parent domain for routing purposes.
REGEXP_SUFFIX = re.compile(
    r"\\\.([a-z0-9-]+(?:\\\.[a-z0-9-]+)+)\$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DomainRule:
    kind: str
    value: str
    attributes: frozenset[str]


@dataclass(frozen=True)
class IncludeRule:
    category: str
    required_attributes: frozenset[str]
    excluded_attributes: frozenset[str]


ParsedRecord = Union[DomainRule, IncludeRule]


def fetch_category(category: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", category):
        raise ValueError(f"Invalid V2Fly category name: {category!r}")
    with urlopen(BASE_URL + category, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def valid_domain(value: str) -> bool:
    """Validate DNS labels; one-label TLD entries (for example 'google') are valid."""
    value = value.strip().rstrip(".").lower()
    if not value or len(value) > 253:
        return False
    labels = value.split(".")
    return all(
        1 <= len(label) <= 63 and DOMAIN_LABEL.fullmatch(label) is not None
        for label in labels
    )


class DomainListConverter:
    def __init__(self, fetcher: Callable[[str], str] = fetch_category):
        self.fetcher = fetcher
        self.parsed_cache: dict[str, tuple[ParsedRecord, ...]] = {}
        self.expanded_cache: dict[str, tuple[DomainRule, ...]] = {}
        self.visited_categories: set[str] = set()

    def parse_category(self, category: str) -> tuple[ParsedRecord, ...]:
        if category in self.parsed_cache:
            return self.parsed_cache[category]

        self.visited_categories.add(category)
        source = self.fetcher(category)
        records: list[ParsedRecord] = []

        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            parts = line.split()
            token = parts[0]

            if token.startswith("include:"):
                child = token.partition(":")[2].strip()
                if not child or not re.fullmatch(r"[A-Za-z0-9_-]+", child):
                    raise ValueError(f"{category}:{line_number}: invalid include target {child!r}")

                required: set[str] = set()
                excluded: set[str] = set()
                for field in parts[1:]:
                    if field.startswith("@-") and len(field) > 2:
                        excluded.add(field[2:].lower())
                    elif field.startswith("@") and len(field) > 1:
                        required.add(field[1:].lower())
                    else:
                        raise ValueError(
                            f"{category}:{line_number}: unsupported include selector {field!r}"
                        )
                records.append(
                    IncludeRule(child, frozenset(required), frozenset(excluded))
                )
                continue

            if ":" in token:
                kind, value = token.split(":", 1)
            else:
                # V2Fly defines an unprefixed domain as shorthand for domain:.
                kind, value = "domain", token

            kind = kind.lower()
            value = value.strip().lower().rstrip(".")
            if kind not in {"domain", "full", "keyword", "regexp"}:
                raise ValueError(f"{category}:{line_number}: unknown rule type {kind!r}")
            if not value:
                raise ValueError(f"{category}:{line_number}: empty {kind} rule")
            if kind in {"domain", "full"} and not valid_domain(value):
                raise ValueError(f"{category}:{line_number}: invalid domain {value!r}")

            attributes: set[str] = set()
            for field in parts[1:]:
                if field.startswith("@") and len(field) > 1 and not field.startswith("@-"):
                    attributes.add(field[1:].lower())
                elif field.startswith("&") and len(field) > 1:
                    # Affiliations are build-time metadata, not routing rules.
                    continue
                else:
                    raise ValueError(
                        f"{category}:{line_number}: unsupported rule attribute {field!r}"
                    )

            records.append(DomainRule(kind, value, frozenset(attributes)))

        parsed = tuple(records)
        self.parsed_cache[category] = parsed
        return parsed

    def expand(
        self, category: str = "google", stack: tuple[str, ...] = ()
    ) -> tuple[DomainRule, ...]:
        if category in stack:
            cycle = " -> ".join((*stack, category))
            raise RuntimeError(f"Circular V2Fly inclusion detected: {cycle}")
        if category in self.expanded_cache:
            return self.expanded_cache[category]

        result: set[DomainRule] = set()
        for record in self.parse_category(category):
            if isinstance(record, DomainRule):
                result.add(record)
                continue

            child_rules = self.expand(record.category, (*stack, category))
            for rule in child_rules:
                if not record.required_attributes.issubset(rule.attributes):
                    continue
                if record.excluded_attributes.intersection(rule.attributes):
                    continue
                result.add(rule)

        expanded = tuple(
            sorted(result, key=lambda item: (item.kind, item.value, sorted(item.attributes)))
        )
        self.expanded_cache[category] = expanded
        return expanded


def regexp_fixed_suffix(pattern: str) -> str | None:
    """Return a fixed escaped multi-label DNS suffix ending the regex, if present."""
    match = REGEXP_SUFFIX.search(pattern)
    if not match:
        return None
    suffix = match.group(1).replace(r"\.", ".").lower()
    return suffix if valid_domain(suffix) else None


def is_covered_by_domain(host: str, domain_roots: set[str]) -> bool:
    return any(host == root or host.endswith("." + root) for root in domain_roots)


def render_autoproxy(\n    rules: tuple[DomainRule, ...], min_rule_count: int = MIN_RULE_COUNT\n) -> tuple[str, dict[str, int]]:
    domain_roots = {rule.value for rule in rules if rule.kind == "domain"}
    exact_hosts = {rule.value for rule in rules if rule.kind == "full"}
    keyword_rules = {rule.value for rule in rules if rule.kind == "keyword"}
    regexp_rules = {rule.value for rule in rules if rule.kind == "regexp"}

    # AutoProxy cannot safely represent arbitrary substring rules.
    if keyword_rules:
        examples = ", ".join(sorted(keyword_rules)[:5])
        raise RuntimeError(
            f"Upstream added {len(keyword_rules)} keyword rule(s) that AutoProxy "
            f"cannot faithfully represent (for example: {examples}). Review required."
        )

    # Preserve regex coverage when a regex ends in a fixed DNS suffix. Routing the
    # whole suffix is a safe superset; it may proxy more hosts but will not miss
    # the regex-matched hosts. Unrecognizable regexes stop publication.
    regex_fallbacks: set[str] = set()
    unhandled_regexes: list[str] = []
    for pattern in sorted(regexp_rules):
        suffix = regexp_fixed_suffix(pattern)
        if suffix:
            domain_roots.add(suffix)
            regex_fallbacks.add(suffix)
        else:
            unhandled_regexes.append(pattern)

    if unhandled_regexes:
        examples = "; ".join(unhandled_regexes[:3])
        raise RuntimeError(
            f"Upstream added {len(unhandled_regexes)} regexp rule(s) without a "
            f"safe fixed-domain suffix. Review required: {examples}"
        )

    # A domain rule already covers the same host and all its subdomains, so an
    # exact-host rule beneath it is redundant.
    uncovered_exact_hosts = {
        host for host in exact_hosts if not is_covered_by_domain(host, domain_roots)
    }

    filters = {f"||{domain}^" for domain in domain_roots}
    # AutoProxy matches complete URLs. Anchor each scheme so full: entries match
    # the exact hostname (including an optional port/path), not a literal bare
    # hostname string and not its subdomains.
    for host in uncovered_exact_hosts:
        for scheme in ("http://", "https://", "ws://", "wss://"):
            filters.add(f"|{scheme}{host}^")

    required_roots = {"google.com", "googleapis.com", "gstatic.com", "googleusercontent.com"}
    missing_roots = required_roots - domain_roots
    if missing_roots:
        raise RuntimeError(
            "Core Google domain(s) missing from parsed source: "
            + ", ".join(sorted(missing_roots))
        )

    if len(filters) < min_rule_count:
        raise RuntimeError(
            f"Only {len(filters)} AutoProxy filters were generated; "
            f"expected at least {MIN_RULE_COUNT}. Refusing to publish an incomplete list."
        )

    lines = [
        "[AutoProxy 0.2.9]",
        "! Title: Google domains (V2Fly domain-list-community)",
        "! Homepage: https://github.com/v2fly/domain-list-community",
        "! Source: https://github.com/v2fly/domain-list-community/blob/master/data/google",
        "! Generated automatically by scripts/build_google_autoproxy.py",
        "! V2Fly keyword/unsupported regex syntax is never silently approximated.",
        "",
        *sorted(filters),
    ]
    content = "\n".join(lines) + "\n"
    stats = {
        "categories": 0,  # Filled by caller.
        "source_domain_rules": len(domain_roots),
        "source_full_rules": len(exact_hosts),
        "exact_hosts_emitted": len(uncovered_exact_hosts),
        "regex_rules_broadened_to_suffix": len(regex_fallbacks),
        "autoproxy_filters": len(filters),
    }
    return content, stats


def main() -> int:
    converter = DomainListConverter()
    expanded = converter.expand("google")
    content, stats = render_autoproxy(expanded)
    stats["categories"] = len(converter.visited_categories)

    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"Visited source categories: {stats['categories']}")
    print(f"Domain rules (including fixed regex suffixes): {stats['source_domain_rules']}")
    print(f"Full-host source rules: {stats['source_full_rules']}")
    print(f"Exact hosts needing explicit URL filters: {stats['exact_hosts_emitted']}")
    print(f"Regex rules safely broadened to parent suffix: {stats['regex_rules_broadened_to_suffix']}")
    print(f"Final AutoProxy filters: {stats['autoproxy_filters']}")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
