import unittest

from build_google_autoproxy import (
    DomainListConverter,
    DomainRule,
    render_autoproxy,
    regexp_fixed_suffix,
)


CORE = (
    DomainRule("domain", "google.com", frozenset()),
    DomainRule("domain", "googleapis.com", frozenset()),
    DomainRule("domain", "gstatic.com", frozenset()),
    DomainRule("domain", "googleusercontent.com", frozenset()),
)


class ConverterTests(unittest.TestCase):
    def converter(self, files):
        return DomainListConverter(fetcher=lambda category: files[category])

    def test_bare_domain_and_single_label_tld_are_kept(self):
        converter = self.converter({
            "google": "google.com\nchrome\n# comment\n"
        })
        rules = set(converter.expand())
        self.assertIn(DomainRule("domain", "google.com", frozenset()), rules)
        self.assertIn(DomainRule("domain", "chrome", frozenset()), rules)

    def test_include_required_and_excluded_attributes(self):
        converter = self.converter({
            "google": "include:child @cn @-ads\n",
            "child": (
                "keep.example.com @cn\n"
                "drop-ads.example.com @cn @ads\n"
                "drop-no-cn.example.com @ads\n"
            ),
        })
        rules = set(converter.expand())
        self.assertEqual(
            rules,
            {DomainRule("domain", "keep.example.com", frozenset({"cn"}))},
        )

    def test_nested_include_filters_are_applied(self):
        converter = self.converter({
            "google": "include:child @cn\n",
            "child": "include:grandchild @mobile\n",
            "grandchild": (
                "keep.example.com @cn @mobile\n"
                "drop.example.com @cn\n"
            ),
        })
        rules = set(converter.expand())
        self.assertEqual(
            rules,
            {DomainRule("domain", "keep.example.com", frozenset({"cn", "mobile"}))},
        )

    def test_circular_include_fails_loudly(self):
        converter = self.converter({
            "google": "include:child\n",
            "child": "include:google\n",
        })
        with self.assertRaisesRegex(RuntimeError, "Circular V2Fly inclusion"):
            converter.expand()

    def test_full_host_rules_are_valid_url_anchored_filters(self):
        rules = CORE + (
            DomainRule("full", "endpoint.example.net", frozenset()),
        )
        output, _ = render_autoproxy(rules, min_rule_count=1)
        for scheme in ("http://", "https://", "ws://", "wss://"):
            self.assertIn(f"|{scheme}endpoint.example.net^", output)
        self.assertNotIn("|endpoint.example.net|", output)

    def test_full_host_is_omitted_when_parent_domain_already_covers_it(self):
        rules = CORE + (
            DomainRule("domain", "example.net", frozenset()),
            DomainRule("full", "api.example.net", frozenset()),
        )
        output, _ = render_autoproxy(rules, min_rule_count=1)
        self.assertIn("||example.net^", output)
        self.assertNotIn("|https://api.example.net^", output)

    def test_single_label_tld_becomes_suffix_rule(self):
        output, _ = render_autoproxy(CORE + (
            DomainRule("domain", "google", frozenset()),
            DomainRule("domain", "chrome", frozenset()),
        ), min_rule_count=1)
        self.assertIn("||google^", output)
        self.assertIn("||chrome^", output)

    def test_fixed_regex_suffix_is_preserved_as_safe_domain_superset(self):
        pattern = r"^r+[0-9]+(---|\\.)sn-(2x3|ni5|j5o)\\w{5}\\.xn--ngstr-lra8j\\.com$"
        self.assertEqual(regexp_fixed_suffix(pattern), "xn--ngstr-lra8j.com")
        output, stats = render_autoproxy(
            CORE + (DomainRule("regexp", pattern, frozenset()),),
            min_rule_count=1,
        )
        self.assertIn("||xn--ngstr-lra8j.com^", output)
        self.assertEqual(stats["regex_rules_broadened_to_suffix"], 1)

    def test_unconvertible_regex_fails_instead_of_being_dropped(self):
        with self.assertRaisesRegex(RuntimeError, "without a safe fixed-domain suffix"):
            render_autoproxy(
                CORE + (DomainRule("regexp", r"^.*google.*$", frozenset()),),
                min_rule_count=1,
            )

    def test_keyword_rule_fails_instead_of_being_dropped(self):
        with self.assertRaisesRegex(RuntimeError, "keyword rule"):
            render_autoproxy(
                CORE + (DomainRule("keyword", "google", frozenset()),),
                min_rule_count=1,
            )


if __name__ == "__main__":
    unittest.main()
