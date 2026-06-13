"""Twitter / X 連結修復工具。

x.com / twitter.com 的貼文（尤其影片）貼到 Discord 不會自動載入預覽，
社群慣用做法是把網域換成第三方 embed 服務（此處用 fixupx.com），
Discord 就能正常顯示預覽。

本模組為純函式、無 discord 相依，方便單獨測試與擴充。
"""

import re

# 只比對貼文連結（含 /status/<id>），避免把個人首頁、搜尋等無意義連結也轉掉。
# 涵蓋 x.com 與 twitter.com（含 www. / mobile. 子網域）。
TWITTER_STATUS_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"(?P<path>[A-Za-z0-9_]+/status/\d+(?:/(?:photo|video)/\d+)?)"
    r"(?P<query>\?[^\s]*)?",
    re.IGNORECASE,
)

# 替代用的可預覽網域。
FIXUP_DOMAIN = "fixupx.com"


def rewrite_twitter_links(content: str) -> str | None:
    """將內容中的 x.com / twitter.com 貼文連結轉成 fixupx.com 版本。

    回傳：
        - 有可轉連結：所有轉好的網址，多個以換行串接。
        - 沒有可轉連結：None。
    """
    if not content:
        return None

    fixed_links: list[str] = []
    seen: set[str] = set()
    for match in TWITTER_STATUS_RE.finditer(content):
        # 去掉追蹤用 query string，連結較乾淨且不影響預覽。
        new_url = f"https://{FIXUP_DOMAIN}/{match.group('path')}"
        if new_url not in seen:
            seen.add(new_url)
            fixed_links.append(new_url)

    if not fixed_links:
        return None

    return "\n".join(fixed_links)
