# Google Domain AutoProxy

Automatically converts the `google` category from [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) into a ZeroOmega/SwitchyOmega-compatible AutoProxy list.

## Subscribe in ZeroOmega

- Rule list format: **AutoProxy**
- Rule list URL:

  `https://raw.githubusercontent.com/steveji2021/google-domain-autoproxy/main/google-autoproxy.txt`

- Rule-list matched profile: choose your **Google Proxy** profile.
- In Auto Switch, use **`+system`** as the default profile so non-matching requests inherit the Windows system proxy.

Create a proxy profile named Google Proxy with HTTP host `127.0.0.1`, port `7897` (your Clash Verge Rev mixed port).

## Updating

GitHub Actions runs daily at 02:23 UTC (10:23 China Standard Time) and can also be started manually from the Actions tab using **Update Google AutoProxy list → Run workflow**.

The workflow:
1. Fetches V2Fly's `data/google` category.
2. Recursively expands `include:` categories and honors inclusion attribute filters.
3. Converts bare and `domain:` entries to domain-and-subdomain filters, including single-label TLD categories such as `.google` and `.chrome`.
4. Converts `full:` entries to URL-anchored exact-host filters for HTTP, HTTPS, WS, and WSS. Exact-host filters already covered by a broader domain rule are omitted as redundant.
5. Converts regex rules with a fixed DNS suffix to a safe parent-domain routing rule. This can proxy a broader set of hosts under that suffix, but it will not miss the regex-matched hosts.
6. Fails rather than silently publishing if an unsupported keyword rule or an unrecognized regex is added upstream.
7. Runs regression tests before generation and commits `google-autoproxy.txt` only when its contents change.

The workflow uses the repository's built-in `GITHUB_TOKEN`; no personal access token or Gist is needed.

## Conversion limitations

- Arbitrary `keyword:` rules cannot be faithfully represented as domain-only AutoProxy filters, so the build fails if V2Fly adds one.
- Regex rules are accepted only when a fixed escaped multi-label suffix can be safely extracted. Other regex forms stop publication for review.
- V2Fly attributes such as `@ads` and `@cn` are retained for selective `include:` processing. In the main Google list, all directly included rules are included regardless of their attributes.
- This is an upstream domain-routing list, not a guarantee that every Google product endpoint is covered. Upstream category contents can change.

## Tests and local generation

Requires Python 3.12.

Run regression tests:

```bash
python -m unittest discover -s scripts -p "test_*.py" -v
```

Generate the list:

```bash
python scripts/build_google_autoproxy.py
```
