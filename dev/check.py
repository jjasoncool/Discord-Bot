"""檢查 dev/ 歸檔的格式與連結；人或 AI 改完歸檔後跑一次。

架構定位：repo 根目錄的文件工具，不屬於 src/ 的任何一層、不進容器，只用標準庫。
上層：手動執行（交接檔「歸檔放哪」與每個歸檔檔開頭的備註要求改完就跑）。下層：只讀檔案。

介面：
- `python3 dev/check.py`：在哪個目錄執行都可以；全部通過印「dev/ 檢查通過」、回 0，有問題逐條列出、回 1。

規則：
- 只讀不寫。
- 主題檔（`dev/<分組>/*.md`）：開頭有給 AI 的備註與「整理到」日期；上半部四個標題加「原文」順序固定；
  原文每段一組 `<details>`；目錄表與段落一一對應；「整理到」不比最新一段舊；README「依日期」每段一列、「依領域」列到這個檔。
- 每月重點（`dev/journal/*.md`）：有備註與「整理到」；只有「這個月的重點」一個大標題；README 流水帳表的重點數一致。
- 連結：dev/、交接檔、AGENTS.md 裡連到 .md 的連結要找得到檔與錨點；交接檔 `@meta` 的 `history:` 要指到存在的檔。

例外與決策：
- 原文裡連到程式檔的舊路徑不算錯：程式會搬，原文照當時的樣子留著。
- 原文本來就壞的站內錨點（指向當年交接檔的舊標題）列在 KNOWN_BROKEN，只准減不准增；修好一個就從清單拿掉。
- 錨點照 GitHub 的規則算（小寫、去標點、空白換連字號、重複加 -1、-2）；程式碼區塊與 HTML 註解裡的 # 不算標題。
"""
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = os.path.join(ROOT, "dev")
HUMAN_HEADINGS = ["一頁看懂", "時間線", "定案與理由", "踩過的坑", "原文"]
JOURNAL_HEADINGS = ["這個月的重點"]

# (檔案, 連結目標)：拆檔前原文就點不到的錨點
KNOWN_BROKEN = Counter({
    ("dev/admin/console.md", "#需要群主介入的狀況私訊重新偵測按鈕管理面板2026-10-29-規劃未動工"): 1,
    ("dev/ai/memory.md", "#ai-偶爾插話--閒聊功能二已上線c-4-待做"): 1,
    ("dev/ai/memory.md", "#使用者指令記憶-remember-未來工作"): 1,
    ("dev/ai/comfyui.md", "#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3"): 1,
    ("dev/ai/search.md", "#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3"): 1,
    ("dev/ai/askai.md", "#使用者指令記憶-remember-未來工作"): 2,
    ("dev/architecture/code-structure.md", "#活動自動發布連結指向錯誤--重複建活動2026-09-22-已實作待部署驗證"): 1,
})

DATE = r"\d{4}-\d{2}-\d{2}"
problems = []


def rel(path):
    return os.path.relpath(path, ROOT)


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n")


def visible(lines):
    """回傳 (行號, 行)，略過程式碼區塊與 HTML 註解裡的行。"""
    fenced = in_comment = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_comment = True
            continue
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield i, line


def slug(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def headings(lines):
    """回傳 [(行號, 層級, 文字, 錨點)]。"""
    seen, out = defaultdict(int), []
    for i, line in visible(lines):
        m = re.match(r"^(#{1,6}) (.*)$", line)
        if m:
            base = slug(m.group(2))
            n = seen[base]
            out.append((i, len(m.group(1)), m.group(2), base if n == 0 else f"{base}-{n}"))
            seen[base] += 1
    return out


_anchor_cache = {}


def anchors_of(path):
    if path not in _anchor_cache:
        _anchor_cache[path] = {a for _, _, _, a in headings(read_lines(path))}
    return _anchor_cache[path]


def check_links(path):
    broken = Counter()
    for _, line in visible(read_lines(path)):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            # 原文裡的正規表示式、範例寫法（`](\d{2})`、`](url)`）不是連結
            if "\\" in target or not (target.startswith("#") or "/" in target or "." in target):
                continue
            file_part, _, anchor = target.partition("#")
            dest = path if not file_part else os.path.normpath(os.path.join(os.path.dirname(path), file_part))
            if not os.path.exists(dest):
                # 原文裡連到程式檔的舊路徑不算錯；連到文件的要找得到
                if file_part.endswith(".md") or rel(dest).startswith("dev"):
                    problems.append(f"{rel(path)}：連到不存在的檔 {target}")
                continue
            if anchor and dest.endswith(".md") and anchor not in anchors_of(dest):
                broken[(rel(path), "#" + anchor if not file_part else target)] += 1
    for key, n in broken.items():
        allowed = KNOWN_BROKEN.get(key, 0)
        if n > allowed:
            problems.append(f"{key[0]}：錨點不存在 {key[1]}")
    for key, allowed in KNOWN_BROKEN.items():
        if key[0] == rel(path) and broken.get(key, 0) < allowed:
            problems.append(f"{key[0]}：KNOWN_BROKEN 裡的 {key[1]} 已經修好或不見了，從清單拿掉")


def ai_note_through(path, lines):
    text = "\n".join(lines[:30])
    m = re.search(r"<!-- 給 AI.*?整理到：(" + DATE + r").*?-->", text, re.S)
    if not m:
        problems.append(f"{rel(path)}：開頭沒有給 AI 的備註或「整理到」日期")
        return None
    return m.group(1)


def readme_rows():
    lines = read_lines(os.path.join(DEV, "README.md"))
    links = set()
    journal = {}
    for _, line in visible(lines):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            links.add(target)
        m = re.match(r"^\| \[(\d{4}-\d{2})\]\(journal/\1\.md\) \| (\d+) \|", line)
        if m:
            journal[m.group(1)] = int(m.group(2))
    return links, journal


def check_topic(path, readme_links):
    lines = read_lines(path)
    through = ai_note_through(path, lines)
    hs = [h for h in headings(lines) if h[1] == 2]
    names = [h[2] for h in hs[:len(HUMAN_HEADINGS)]]
    if names != HUMAN_HEADINGS:
        problems.append(f"{rel(path)}：上半部標題應該是 {'、'.join(HUMAN_HEADINGS)}，實際是 {'、'.join(names)}")
        return
    sections = hs[len(HUMAN_HEADINGS):]
    start_of_raw = hs[len(HUMAN_HEADINGS) - 1][0]
    first_section = sections[0][0] if sections else len(lines)

    toc = {}
    for line in lines[start_of_raw:first_section]:
        m = re.match(r"^\| (" + DATE + r") \| \[.*?\]\(#(.*?)\) \| .* \|$", line)
        if m:
            toc[m.group(2)] = m.group(1)
    section_anchors = [a for _, _, _, a in sections]
    for a in section_anchors:
        if a not in toc:
            problems.append(f"{rel(path)}：段落 #{a} 沒有目錄列")
    for a in toc:
        if a not in section_anchors:
            problems.append(f"{rel(path)}：目錄列 #{a} 找不到段落")

    bounds = [s[0] for s in sections] + [len(lines)]
    for (i, _, _, a), end in zip(sections, bounds[1:]):
        body = lines[i:end]
        opens = sum(1 for l in body if l.strip() == "<details>")
        closes = sum(1 for l in body if l.strip() == "</details>")
        if opens != 1 or closes != 1:
            problems.append(f"{rel(path)}：段落 #{a} 的 <details> 應該剛好一組（現在 {opens} 開 {closes} 關）")

    if through and toc:
        newest = max(toc.values())
        if through < newest:
            problems.append(f"{rel(path)}：上半部只整理到 {through}，最新一段是 {newest}；更新上半部與「整理到」")

    target = rel(path)[len("dev/"):]
    if target not in readme_links:
        problems.append(f"dev/README.md：「依領域」沒有列到 {target}")
    for a in section_anchors:
        if f"{target}#{a}" not in readme_links:
            problems.append(f"dev/README.md：「依日期」缺 {target}#{a}")


def check_journal(path, readme_journal):
    lines = read_lines(path)
    ai_note_through(path, lines)
    names = [h[2] for h in headings(lines) if h[1] == 2]
    if names != JOURNAL_HEADINGS:
        problems.append(f"{rel(path)}：大標題應該只有 {'、'.join(JOURNAL_HEADINGS)}，實際是 {'、'.join(names)}")
        return
    points = [l for _, l in visible(lines) if re.match(r"^- \*\*\d{2}-\d{2} ", l)]
    month = os.path.basename(path)[:-3]
    if readme_journal.get(month) != len(points):
        problems.append(f"dev/README.md：流水帳 {month} 的重點數應該是 {len(points)}")


def check_history():
    path = os.path.join(ROOT, "AI_HANDOFF_AND_TODO.md")
    for line in read_lines(path):
        m = re.match(r"^history: (\S+)$", line)
        if m and not os.path.exists(os.path.join(ROOT, m.group(1))):
            problems.append(f"AI_HANDOFF_AND_TODO.md：history 指到不存在的檔 {m.group(1)}")


def main():
    readme_links, readme_journal = readme_rows()
    md_files = []
    for dirpath, _, files in os.walk(DEV):
        for name in sorted(files):
            if name.endswith(".md"):
                md_files.append(os.path.join(dirpath, name))
    for path in sorted(md_files):
        sub = rel(path)[len("dev/"):]
        if sub == "README.md":
            pass
        elif sub.startswith("journal/"):
            check_journal(path, readme_journal)
        else:
            check_topic(path, readme_links)
        check_links(path)
    for name in ("AI_HANDOFF_AND_TODO.md", "AGENTS.md"):
        check_links(os.path.join(ROOT, name))
    check_history()

    if problems:
        print(f"dev/ 檢查有 {len(problems)} 個問題：")
        for p in problems:
            print("  -", p)
        return 1
    print(f"dev/ 檢查通過（{len(md_files)} 個檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
