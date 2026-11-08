# Google Domain AutoProxy

Automatically converts the `google` category from [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) into a ZeroOmega/SwitchyOmega-compatible AutoProxy list.

## Subscribe in ZeroOmega

- Rule list format: **AutoProxy**
- Rule list URL:

  `https://raw.githubusercontent.com/steveji2021/google-domain-autoproxy/main/google-autoproxy.txt`

- Rule-list profile / matched profile: choose your **Google Proxy** profile.
- In Auto Switch, use **`+system`** as the default profile so non-matching requests inherit the Windows system proxy.

Create a proxy profile named Google Proxy with HTTP host `127.0.0.1`, port `7897` (your Clash Verge Rev mixed port).

## Updating

GitHub Actions runs daily at 02:23 UTC and can also be started manually from the Actions tab using **Update Google AutoProxy list → Run workflow**.

The workflow:
1. Fetches V2Fly's `data/google` category.
2. Recursively expands `include:` categories.
3. Converts `domain:` entries to AutoProxy domain-and-subdomain rules and `full:` entries to exact-host rules.
4. Commits `google-autoproxy.txt` only when its contents change.

The workflow uses the repository's built-in `GITHUB_TOKEN`; no personal access token or Gist is needed.

## Notes and limitations

- AutoProxy cannot faithfully express V2Fly `keyword:` or `regexp:` entries. Those are skipped rather than approximated. The Actions log reports the count of skipped entries.
- This is a domain-routing list, not a guarantee that every Google product endpoint is covered. Upstream category contents can change.
- The raw subscription URL is stable; ZeroOmega can periodically refresh it.
- The workflow needs repository Actions enabled and the default workflow token permission **Read and write permissions**. The workflow also declares `contents: write`.

## Local generation

Requires Python 3. Run:

```bash
python scripts/build_google_autoproxy.py
```
