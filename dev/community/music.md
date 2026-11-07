# 點歌機器人

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-19
-->

> 現況、待決與待做以交接檔為準：[點歌機器人](../../AI_HANDOFF_AND_TODO.md#點歌機器人)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管語音頻道裡的點歌機器人：播放與快取、按鈕面板、歌單，以及語音斷線後怎麼接回去。

- **04-18**：核心功能上線。按鈕面板代替斜線指令、點歌用 Modal、雙佇列（主歌單循環＋插播優先）、本地快取與峰值正規化；DAVE 加密下改走 `FFmpegPCMAudio`。
- **04-23**：面板加「⭐ 收藏」按鈕，私訊歌名給按的人；私訊發送收進 `utils/dm_notifier.py`。
- **06-13～06-20**：「停止」改成會重抓線上歌單的「重置歌單」，再擴充成「編輯歌單 🎚️」：設定檔可以填多個歌單，勾幾個就合併播放，免重啟。點歌的人離開頻道 5 秒沒回來，他點的歌就移除。
- **10-15～10-16 關鍵轉折**：使用者回報 bot 一直自我斷線。查出 discord.py 2.7.1 自己重連的同時，播放器也介入建新連線，舊連線的 task 變成殭屍，30 秒後把新連線踢掉。改成先等 discord.py 自己接回，接不回才在同一個連線物件上重連，被打斷的歌從斷點續播。
- **10-19**：重連那半有效（之後 10 次斷線都在 0.6～2.2 秒內自己接回），但斷點續播會卡住，卡了約 35 小時沒播別首。

**歸檔時（10-19）的狀態**

- [x] 核心播放、按鈕面板、本地快取上線（04-18）
- [x] 多歌單下拉、點歌者離開就移除他的歌（06-13～06-20）
- [x] 斷線後先等 discord.py 自己接回，接不回才在同一連線上重連（10-16）
- [ ] 斷點續播會卡住，還沒查因、沒修，排在面試之後
- [ ] 多歌單部署後的 7 項驗證（原文沒記結果）
- [ ] 面板改用共用置底元件（09-29 暫緩）
- [ ] pause／resume、快取 LRU 清理、播放紀錄與點歌統計

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 04-12 | 語音重連死循環 | 改用 `guild.voice_client` 認領，不再無限噴 Already connected 灌爆 Docker log |
| 04-18 | 點歌機器人核心上線（P0 完成、P1 主體完成） | 剩 pause／resume、多歌單、快取 LRU、播放紀錄等 |
| 04-23 | 抽出 `dm_notifier`、面板加收藏按鈕 | 關鍵字監控命中那段約 60 行縮成一行 |
| 06-13 | 「停止」改「重置歌單 ♻️」；點歌者離開自動移除他的歌 | 先抓成功才換歌單；寬限 5 秒、移除後簡短公告 |
| 06-20 | 多歌單下拉，可複選合併播放 | 按鈕改名「編輯歌單 🎚️」；7 項待部署後驗證 |
| 09-29 | 討論音樂面板改用共用置底元件 | 暫緩 |
| 10-14 | 面板 id 與歌單拆成兩個檔 | `settings/runtime/music.json`、`settings/music_playlists.json` |
| 10-15 | 查「一直自我斷線」 | 語音連線被切 62 次；成因鏈四路獨立覆核一致；升版無解 |
| 10-16 | 實作修法：等 35 秒、同一連線重連、斷點續播 | 14:09 之後 10 次斷線都由 discord.py 自己接回 |
| 10-19 | 發現斷點續播會卡住 | 10-16 15:43 起卡到 10-18 02:40 停機；未修、未查因 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 只設定一個語音頻道，加入語音與發面板都用它 | Discord 語音頻道自帶文字聊天，和語音頻道共用同一個 ID |
| 播放走 `FFmpegPCMAudio`＋discord.py 內建 encoder | `FFmpegOpusAudio` 在 DAVE 加密下會斷續爆音 |
| 快取播放時掃描峰值，等比例增益對齊 -1dB | 保留原始動態 |
| 下載限速 3MB/s，同時只 1 個下載 | 避免搶串流頻寬 |
| 不用 cookie | 小規模使用不需要登入 |
| 收藏只寄私訊，不記檔、不去重 | 符合 MVP |
| 「停止」改成「重置歌單」並重抓線上歌單，`custom_id` 仍是 `music_stop` | 舊按鈕只清插播、跳當前歌，主歌單照播，名稱誤導；線上歌單改了不重啟不會同步；沿用 id 才相容既有面板 |
| 點歌者離開後寬限 5 秒才移除他的歌 | 避免閃斷誤砍 |
| 每個歌單算一個穩定的 `key`，選擇用 key 存 | 跟可能自動抓、會變動的歌單名稱分開 |
| 音樂面板改用共用置底元件暫緩（09-29） | 面板訊息存記憶體、按鈕就地編輯、啟動時有清理流程；要搬得先把面板 id 移到別的檔，上線那次會留一則舊面板要手動刪 |
| 斷線後先等 35 秒讓 discord.py 自己接回 | discord.py 自己的連線逾時是 30 秒，加緩衝；短於 30 秒會和它打架 |
| 介入時在同一個連線物件上 `connect()`，失敗才建新連線 | `connect()` 會先取消舊 task、不留殭屍；另一個做法是取消私有的 `_runner`，版本一換就壞 |
| 被打斷的歌從斷點續播（記已播秒數，ffmpeg `-ss`） | 原文只記「照建議」，沒寫理由 |

## 踩過的坑

- **discord.py 重連時會誤叫醒播放執行緒**：2.7.1 的 `disconnect(cleanup=False)` 在 finally 把 `_connected` set 再 clear；播放執行緒剛好在這時等連線，會放棄播放（只記 DEBUG），這首歌被當成播完。命中率約 8/50。
- **`disconnect()` 不會取消舊連線的 `_poll_voice_ws`**：只有 `connect()`、`soft_disconnect()` 會。舊 task 卡在 30 秒的等待裡變殭屍，逾時後把新連線踢出頻道（新連線收 4014），還以 guild id 拔掉新連線的登記。
- **poller 會被沒接住的例外殺掉**：2.7.1 只接 ConnectionClosed、TimeoutError，10-15 03:55 是 `ClientConnectorDNSError`。這種情況播放器 30 秒後介入是對的。
- **升版解決不了**：2.7.1 是 PyPI 最新版，master 的語音三檔跟它相同，也沒有對應的 upstream issue。
- **`guild._voice_client = None` 是空操作**：Guild 有 `__slots__`，`voice_client` 是讀登記表的 property。
- **斷點續播會卡住**：歌被記成被打斷、要從第 122 秒續播，但 `voice_client` 一直回報還在播，每約 2.5 秒「排回稍後重試」一次，兩個 log 檔共 30,609＋16,735 行 WARNING，期間沒播別首。10-18 重啟後沒再出現，下次語音斷線很可能再卡。
- **DAVE 加密偶爾讓某段短暫加速**：AudioPlayer 20ms 的 frame timing 在加密耗時過長時會追趕，是套件層級的問題，程式解不了。
- **語音斷線的統計只從 09-29 起**：discord logger 那天才寫進檔案。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-06-20 | [多歌單下拉與合併播放](#變更紀錄多歌單下拉可複選合併播放歸檔-2026-07-02原-2026-06-20) | 設定檔可填多個歌單，按「編輯歌單」彈出多選清單、勾幾個合併播幾個，免重啟；部署後待驗證。 |
| 2026-06-13 | [點歌者離開移除他的歌](#點歌者離開自動移除其點的歌歸檔-2026-06-20原-2026-06-13) | 點歌的人離開音樂頻道 5 秒沒回來，就移除他點的歌、正在播的跳過，並在頻道簡短公告。 |
| 2026-06-13 | [「停止」按鈕改成重置歌單](#音樂停止按鈕改為重置歌單--重載線上歌單歸檔-2026-06-20原-2026-06-13) | 舊「停止」名稱誤導，改成重抓線上歌單、先抓成功才換；custom_id 沿用以相容既有面板。 |
| 2026-04-23 | [私訊模組抽出與收藏按鈕](#dm-通知模組抽出--音樂面板收藏按鈕歸檔-2026-04-23) | 私訊發送收成 utils/dm_notifier.py，音樂面板加「⭐ 收藏」按鈕，把歌名私訊給按的人。 |
| 2026-10-19 | [語音斷線重連競態與續播卡住](#點歌機器人語音斷線自我重連競態的查因修法與-10-19-續播卡住紀錄歸檔-2026-11-07原至-2026-04-18) | 待辦清單、10-15 查出重連競態的成因鏈、10-16 修法，以及 10-19 發現斷點續播會卡住、未修。 |
| 2026-04-18 | [點歌機器人完整實作（04-18）](#點歌機器人-music-bot-完整實作歸檔-2026-04-18) | 核心功能上線時的架構、設計決策、已實作功能、音訊鏈路與已知限制（DAVE 加密相關）。 |

## 變更紀錄：多歌單下拉（可複選合併播放）（歸檔 2026-07-02，原 2026-06-20）

> 設定檔可填多個歌單，按「編輯歌單」彈出多選清單、勾幾個合併播幾個，免重啟；部署後待驗證。

<details>
<summary>展開原文（約 2,518 字）</summary>

<!-- @meta
id: music-multi-playlist-select
type: FEATURE
status: implemented_pending_verify
last_confirmed: 2026-06-20
-->

**需求：** 控制面板加一個 Discord 多選下拉（multi-select），可勾選一個歌單只播該歌單、勾多個則合併播放、全勾＝全部合併；預設全部合併。需相容現況的單一歌單設定，且歌單名稱可自動抓 YouTube 標題（不用手打）。

**設定檔（`src/settings/music_runtime.json`）— key 為 `playlist_url`，多型：**
- 字串：`"playlist_url": "https://...&list=..."`
- 字串陣列：`"playlist_url": ["url1", "url2"]`
- 物件陣列：`"playlist_url": [{"name": "華語", "url": "..."}, {"url": "..."}]`（`name` 可省略＝自動抓 YouTube 歌單標題）
- `active_playlists`（選用）：`"all"` 或 key/名稱陣列；記住使用者下拉選擇、重啟後沿用，預設全部。machine 寫入用 key。
- **向後相容**：沒有 `playlist_url` 時自動讀舊 key `default_playlist_url`（字串）。

**識別與命名設計：**
- 每個歌單算一個穩定 `key`（`list=` id ＞ video id ＞ url 截斷），下拉 value 與 `active_playlists` 持久化都用 key，與「可能自動抓/變動的名稱」解耦。
- 顯示名稱：自訂 name ＞ 自動抓的 YouTube 標題 ＞ 後備。自動標題在背景抓取（`YTDLSource.extract_playlist_title()` 用 `playlistend=1` 快速；載入歌單時也順手快取），抓到後 `refresh_panel()`。

**變更：**
- `src/music/config.py`：新增 `playlist_key()` 與 `Playlist(key,url,name=None)`；`MusicConfig` 用 `playlists`/`active_keys`，property `default_playlist_url`/`active_urls`/`has_playlists`。`_parse_playlists()` 解析多型 `playlist_url`（＋舊 key 相容），`_resolve_active()` 回 key（接受 key 或名稱）。watcher 監看 `playlist_url`/`default_playlist_url`/`active_playlists`。
- `src/music/ytdl.py`：`_extract_playlist_sync()` 改回傳 `(title, entries)`；新增 `extract_playlist_title()`。
- `src/music/player.py`：`_playlist_titles` 標題快取；`_fetch_playlist_songs()` 順手快取標題；新增 `load_active_playlists()`/`_rebuild_main_from_urls()`（多歌單合併、先抓成功才換）/`set_active_playlists(keys)`（切換＋持久化）/`resolve_playlist_titles()`/`display_name()`。`reload_playlist()` 重載「目前選取集合」。
- `src/music/announcer.py`：`PlaylistSelect`（value=key, label=顯示名稱）放進 **ephemeral 彈出面板** `PlaylistEditView`，不常駐主面板。主面板「重置歌單 ♻️」按鈕改名 **「編輯歌單 🎚️」**（custom_id 仍 `music_stop` 相容既有面板）。
- `src/music/cog.py`：啟動載入改 `load_active_playlists()`，gate 改 `has_playlists`；新增背景 `_prewarm_playlist_titles()`（預抓名稱）；新增 `refresh_playlist_config()`（force_reload + 抓名稱，不動佇列）。
- **「編輯歌單 🎚️」按鈕流程**：按下 → `refresh_playlist_config()` 立即重讀 `music_runtime.json`（不等 5 秒 watcher）+ 補抓歌單名稱 → 若 **≥2 個歌單**則彈出 ephemeral 多選清單讓使用者挑（選好由 `PlaylistSelect.callback` → `set_active_playlists()` 重建並持久化）；若 **0~1 個**則直接 `reload_playlist()` 重載最新線上歌單。使用者編輯 `playlist_url`（新增/刪改歌單）後按一下即套用，**免重啟**。

**待驗證（部署後）：** ① 單一歌單／舊 `default_playlist_url`：按「編輯歌單」直接重載、不彈清單；② 填多個歌單：按「編輯歌單」彈出 ephemeral 多選清單，預設全勾合併；③ 清單勾單一個只播該歌單、勾多個合併；④ 沒填 name 時清單顯示 YouTube 歌單標題；⑤ 抓取失敗保留舊歌單；⑥ 重啟後沿用上次選擇；⑦ 編輯設定檔新增歌單後，按「編輯歌單」即出現新歌單（免重啟）。

**待 user 提供：** 把第二條（含以後更多）歌單連結填進 `playlist_url`（名稱可不填）。

</details>

## 點歌者離開自動移除其點的歌（歸檔 2026-06-20，原 2026-06-13）

> 點歌的人離開音樂頻道 5 秒沒回來，就移除他點的歌、正在播的跳過，並在頻道簡短公告。
>
> 關鍵字：music、drop_requests_by、on_voice_state_update、寬限 5 秒

<details>
<summary>展開原文（約 663 字）</summary>

<!-- @meta
id: music-drop-requests-on-leave
type: FEATURE
status: confirmed
last_confirmed: 2026-06-13
-->

**需求：** 有人進音樂頻道點歌就跑走，偵測其離開後自動砍掉他點的歌——未播放的移除、正在播放的等同跳過停止。

**設計（資料已就緒：`song.requested_by_id` 點歌時已記錄）：**
- `MusicQueue.remove_interrupts_by(user_id)`（`src/music/queue.py`）：移除某人尚未播放的插播歌。
- `MusicPlayer.drop_requests_by(user_id)`（`src/music/player.py`）：未播放的移除 + 正在播的若是他點的則 `voice_client.stop()` 跳過。主歌單歌 `requested_by_id=None` 不會誤砍。
- `MusicCog.on_voice_state_update` + `_handle_requester_left`（`src/music/cog.py`）：偵測離開音樂頻道（完全離開或切頻道都算）→ **寬限 5 秒**，若仍未回來才移除 → 在頻道發**簡短公告**。

**行為共識：** 寬限 5 秒（避免閃斷誤砍）、移除後頻道簡短公告。
**待驗證：** ① 點歌後離開 5 秒內回來不砍；② 超過 5 秒砍掉且公告；③ 正在播他的歌會直接跳過；④ 主歌單歌不受影響。

</details>

## 音樂「停止」按鈕改為「重置歌單 + 重載線上歌單」（歸檔 2026-06-20，原 2026-06-13）

> 舊「停止」名稱誤導，改成重抓線上歌單、先抓成功才換；custom_id 沿用以相容既有面板。
>
> 關鍵字：music、reload_playlist、先抓成功才換、後改名編輯歌單

<details>
<summary>展開原文（約 701 字）</summary>

<!-- @meta
id: music-reset-reload-playlist
type: FEATURE
status: confirmed
last_confirmed: 2026-06-13
-->

**背景：** 舊「停止」按鈕(player.stop())其實只清點歌插播+跳當前歌，主歌單仍續播，名稱誤導；且線上歌單(default_playlist_url)改了內容後不重啟不會同步。

**變更：**
- 按鈕 `停止/⏹` → `重置歌單/♻️`（custom_id 仍為 `music_stop` 以相容既有面板），method 改名 `reset_playlist`（`src/music/announcer.py`）。
- 新增 `MusicPlayer.reload_playlist()`（`src/music/player.py`）：重新抓取 `default_playlist_url` 最新清單 → 清空點歌+舊主歌單 → 換上新清單 → 套用 shuffle → 跳過當前舊歌續播。**先抓成功才換**，抓取失敗/空清單則保留舊歌單回傳 None。`_reloading` 旗標防重複觸發。
- 抽出 `_fetch_playlist_songs()` 純抓取 helper，`add_to_playlist()` 與 `reload_playlist()` 共用。

**備註：** `MusicPlayer.stop()` 已無呼叫者（dead code），暫時保留未刪。
> 後續 2026-06-20「多歌單下拉」已把此按鈕再改名為「編輯歌單 🎚️」並擴充，詳見 handoff。

</details>

## DM 通知模組抽出 + 音樂面板收藏按鈕（歸檔 2026-04-23）

> 私訊發送收成 utils/dm_notifier.py，音樂面板加「⭐ 收藏」按鈕，把歌名私訊給按的人。
>
> 關鍵字：dm_notifier、resolve_user、send_dm、music favorite button、persistent custom_id

<details>
<summary>展開原文（約 890 字）</summary>

### 改動

①新增 `src/utils/dm_notifier.py`（系統模組層，與 `logger_config.py` 同層），提供四個函式：
- `resolve_user`（user_id → User/Member，`guild.fetch_member` → `bot.fetch_user` → `bot.get_user` → `guild.get_member`）
- `send_dm`（底層發送，吃掉所有例外，回 bool）
- `notify_keyword_hit`
- `notify_song_liked`

所有 discord DM 發送的共通 user resolution + 例外處理集中於此。

②`commands/user_commands.py` 的 keyword 監控命中段（原 ~60 行 user resolution + embed + try/except）縮到一行：
```python
await notify_keyword_hit(self.bot, user_id, message, found_keywords, guild=message.guild)
```

③`music/announcer.py` 的 `MusicControlView` 第一排加入 `⭐ 收藏` Secondary 按鈕（順序：點歌 → 歌單 → 收藏），按下後寄 DM 給按鈕觸發者（含歌名、長度、YT 連結、縮圖、語音頻道），`custom_id="music_favorite"` 可持久化；失敗給 ephemeral 提示「你的私訊已關閉」。

④純 DM 無記檔、無 de-dup（按幾次寄幾次，符合 MVP）。

### 附帶整理

`src/services/migrate_json_to_sqlite.py` 搬到 `src/scripts/`（用 `git mv` 保留歷史，與 `migrate_emoji_text_format.py` / `reembed_pgvector.py` 同性質），docstring 執行路徑同步更新。

</details>

## 點歌機器人：語音斷線自我重連競態的查因、修法與 10-19 續播卡住紀錄（歸檔 2026-11-07，原至 2026-04-18）

> 待辦清單、10-15 查出重連競態的成因鏈、10-16 修法，以及 10-19 發現斷點續播會卡住、未修。
>
> 關鍵字：點歌、music、語音斷線、重連競態、殭屍連線、_poll_voice_ws、斷點續播、discord.py 2.7.1、ensure_voice、voice_client 仍在播放

<details>
<summary>展開原文（約 3,735 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「點歌機器人專區」區塊（`music-bot`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 核心 P0 + P1 主體已完成並上線運作。
> **完整架構 / 設計決策 / 已實作功能 / 音訊鏈路 / 已知限制 / Config 已歸檔至 `TODO-completed.md` 的「點歌機器人 Music Bot 完整實作（歸檔 2026-04-18）」。**

### 點歌機器人 TODO


**P1（體驗優化）：**
- [ ] `/pause` 與 `/resume` 按鈕
- [ ] 音樂面板改用共用置底元件 `utils.panel_bump.PanelBumper`（2026-09-29 決定**暫緩**：面板訊息存記憶體、按鈕狀態就地 edit、啟動時有清理流程、面板 id 在 `settings/runtime/music.json`、歌單在 `settings/music_playlists.json`（10-14 已拆開）；要搬得先把面板 id 移到別的檔，上線那次會留一則舊面板要手動刪）
- [x] 多歌單管理（多歌單下拉，可複選合併播放）— 2026-06-20，詳見 `TODO-completed.md` 歸檔
- [ ] 快取空間管理（LRU 清理、磁碟用量監控）

**P2（進階功能）：**
- [ ] 歷史播放紀錄
- [ ] 使用者點歌統計
- [ ] DAVE 加速問題追蹤（等 discord.py 後續版本優化）

### 語音斷線後的自我重連競態（2026-10-15 查因；修法待定案）


**現象**：使用者回報音樂 bot「一直自我斷線」。log 統計（09-29 起 discord logger 才進檔，統計腳本在 scratchpad 的 `voice_stats.py`）：語音 websocket 被切 62 次（1006 ×47、1001 ×5、30 秒沒訊息 ×10），每天 0～7 次、沒有趨勢。其中 45 次 discord.py 1～6 秒自己接回、歌照播（Discord 上仍看得到 bot 閃退重進一次）；8 次播放器在 1～3 秒內介入、9 次在 30～34 秒介入。10-08 起 6 次快速介入全部變成「掉兩次、無聲 63～65 秒、連丟兩首」（10-08、10-09、10-14、10-15 ×3）。10-14 的 11 次加入有 9 次是部署重啟；10-15 的 10 次有 3 次重啟、7 次介入。

**成因鏈（已定案，四路獨立覆核一致）**：
1. 外部：語音連線被切（多為 1006），與主 gateway 的 RESUMED 只有 12/62 同時，是語音連線單獨掉、不是整機網路，也不是程式造成（event loop 卡頓的紀錄都不在斷線附近）。
2. discord.py 2.7.1 自己重連時，`VoiceConnectionState.disconnect(cleanup=False)` 的 finally 會把 `_connected` set 再 clear（喚醒等待者；自 2.4.0 起如此）。播放執行緒每 20 ms 檢查一次連線，若恰好在 state 變成 disconnected 之後、flip 之前進入 `wait_until_connected`，會被叫醒、`is_connected()` 仍 False → 放棄播放（DEBUG，log 看不到）→ `after(None)` → 這首歌被當成播完。命中率約 8/50。
3. `_play_next` 半秒後重入 → `ensure_voice` 看到未連線 →「偵測到失效的 voice_client」→ `_force_cleanup_guild_voice` 對舊連線 `disconnect(force=True)` 再 `channel.connect()` 建新連線。`disconnect` 不會取消舊連線的 `_poll_voice_ws` task（只有 `connect()`／`soft_disconnect()` 會），它卡在 `_connect` 的 30 秒 wait_for 裡變殭屍。這是第一次「自我斷線」（約 5 秒無聲）。
4. 30 秒後殭屍逾時 → 對已關閉的 ws poll 到 close code 1000 → `_expecting_disconnect` 早被重設 → 走完整 `disconnect()`：送 channel=None 把新連線踢出頻道（新連線收 4014），並以 guild id 為鍵 `cleanup()`，拔掉的是**新連線**的登記 → 新連線再收不到任何語音事件，`_potential_reconnect` 必等滿 30 秒 →「Reconnect was unsuccessful」→ stop() → 播放器第二次介入。這是第二次「自我斷線」（約 33 秒無聲）。
5. 另一型：discord.py 重連本身卡住（gateway 事件 30 秒沒到，常伴 RESUME 或 endpoint=null），或 poller 被未接住的例外殺死（10-15 03:55 是 `ClientConnectorDNSError`；2.7.1 只接 ConnectionClosed／TimeoutError）。播放執行緒 30 秒逾時後介入，這時介入是對的、沒有殭屍。

**覆核結論**：機制全是舊的——播放器重連碼自 05-11 未改；discord.py 2.7.1 是 PyPI 最新版，master 的語音三檔與 2.7.1 相同，升版無解；沒有對應的 upstream issue（第三方專案 discord-radio 10-06 踩到同類問題，修法是「每個 guild 只允許一個重連、先給 discord.py 幾秒自己接回」）。10-08 第一次「被踢」發生在當天映像重建之前，套件變動假說推翻；10-08 前的快速介入沒被踢是因為當時 gateway 或新連線剛好也卡住，差別只在亞秒級時序。另外 `player.py` 的 `guild._voice_client = None` 是空操作（Guild 有 `__slots__`，`voice_client` 是讀登記表的 property）。

**修法（10-16 已實作、未 commit，見最後盤點紀錄的快照 01；三題照建議：35 秒、同一條連線重連、斷點續播）**：斷線後先讓 discord.py 自己接回，播放器只在它真的接不回來時才介入；介入時在同一個連線物件上 `connect()`（它會先取消舊 task，不留殭屍），失敗才建新連線；被打斷的歌接回去播而不是跳過；等待期間只記 INFO，真的介入才 WARNING。測試用假連線物件守四條底線（時限內接回就不動手、逾時才同物件重連、再失敗才建新連線、被打斷的歌不被跳過），等待走可換時鐘接 `test/fake_clock.py`。

**未定案（選項＋建議）**：
1. 等多久才介入：建議 35 秒（discord.py 自己的連線逾時 30 秒＋緩衝）；短於 30 秒會和它打架。
2. 介入方式：建議同一物件 `connect()`、失敗才建新連線。另一選項是硬清理時另取消私有的 `_runner`，版本一換就壞，不建議。
3. 被打斷的歌：A 從斷點續播（記已播秒數，ffmpeg `-ss`）／B 從頭重播／C 照現在跳下一首。建議 A。
4. 檔案衝突：`player.py`、`cog.py` 有另一批未提交的停機收尾改動。A 等那批先 commit 再改／B 只改重連函式、兩批一起等下次重啟。建議 A。

順帶可做：`settings/logging.json` 把 `discord.player` 暫設 DEBUG，修好後可直接看到「Aborting playback」有沒有再發生；刪掉無效的 `guild._voice_client = None`。

---
- **2026-10-19 新發現（未修、未查因）**：修正上線後重連那半有效（10-16 14:09 之後 10 次斷線都在 0.6～2.2 秒內由 discord.py 自己接回），斷點續播卻會卡住：10-16 15:43 第一次斷線後，播放器把歌記成被打斷、要從第 122 秒續播，但 `voice_client` 一直回報還在播，於是每約 2.5 秒「voice_client 仍在播放，將歌曲排回稍後重試」一次，卡到 10-18 02:40 停機（約 35 小時、`discord_bot.log.1` 30,609 行加 `discord_bot.log` 16,735 行 WARNING），期間沒播別首。10-18 重啟後沒再出現（10-19 中午正常在播），`player.py` 之後沒改過，下次語音斷線很可能再卡。排在面試之後查。

</details>

## 點歌機器人 Music Bot 完整實作（歸檔 2026-04-18）

> 核心功能上線時的架構、設計決策、已實作功能、音訊鏈路與已知限制（DAVE 加密相關）。
>
> 關鍵字：music、yt-dlp、DAVE、按鈕面板、快取、音訊鏈路

<details>
<summary>展開原文（約 2,652 字）</summary>

> 核心功能已上線運作（P0 完成、P1 主體完成），部署後持續運行中。
> 剩餘 P1 體驗優化（pause/resume、多歌單、快取 LRU）與 P2 進階功能（播放紀錄、點歌統計、DAVE 加速追蹤）仍保留在 handoff `點歌機器人 TODO` 區塊。

### 架構

- 模組位置：`src/music/`（9 個檔案）
- 入口橋接：`src/commands/music_commands.py` → `MusicCog`
- 頻道設定：`config.json` 的 `music_voice_channel_id`（由 `/server_manager` 設定）
- 歌單設定：`src/settings/music_runtime.json` 的 `default_playlist_url`
- hot reload watcher：同時監控 `config.json` + `music_runtime.json`，變更後自動重連
- 依賴：`yt-dlp`、`discord.py[voice]>=2.7.1`、`davey>=0.1.5`（DAVE 加密）、`FFmpeg`

### 設計決策

- **只需設定一個語音頻道**：`voice_channel_id` 同時用於加入語音、發送面板
- **語音頻道內建聊天**：Discord 語音頻道自帶文字聊天，與語音頻道共用同一 ID
- **按鈕面板取代 slash command**：控制面板（點歌/跳過/停止/重播/歌單）在語音頻道聊天內自動 bump
- **點歌用 Modal**：按「點歌」按鈕 → 彈出輸入框，支援 URL 或關鍵字
- **點歌排隊不打斷**：點歌加入插播佇列，當前歌曲播完才播點的歌
- **停止只清插播**：停止按鈕只清除使用者點的歌，預設歌單保留
- **本地快取**：首次串流播放 + 背景下載到 `src/music/cache/`，之後從本地播放
- **快取峰值正規化**：快取播放時掃描峰值，等比例增益對齊 -1dB，保留原始動態
- **無 cookie**：小規模使用不需登入
- **FFmpegPCMAudio**：DAVE 加密下最穩定（FFmpegOpusAudio 在 DAVE 下會斷續爆音）

### 已實作功能

- 按鈕控制面板（點歌 / 跳過 / 停止 / 重播 / 歌單）— persistent view
- 點歌 Modal — 支援 YouTube URL 或關鍵字搜尋（`ytsearch`）
- 點歌排隊 — 不打斷當前播放，顯示排隊順位
- 重播按鈕 — 刪除快取 + 重新從 YouTube 抓取並播放當前歌曲
- 換歌自動 bump — 刪舊面板 → 發新面板（「現在播放」embed + 按鈕 + 縮圖）
- 待機面板 — 無歌曲時顯示待機狀態 + 按鈕
- 雙佇列 — 主歌單（循環）+ 插播（優先，不循環）
- 預設歌單自動載入（`extract_flat` 快速解析，邊載入邊播放）
- 本地快取（`src/music/cache/`，opus 原始品質，零損失）
- 快取峰值正規化（`volumedetect` + `volume` 濾鏡，等比例增益）
- 預先快取（prefetch 接下來 3 首，減少切歌延遲）
- 下載限速 3MB/s + Semaphore 同時只 1 個下載（避免搶串流頻寬）
- 版權/私人/已刪除影片自動跳過 + embed 通知 + 從歌單移除
- Runtime 配置 hot reload（config.json + music_runtime.json）
- `/server_manager` 頻道設定整合（語音頻道選項）
- YouTube 縮圖修復（`extract_flat` 模式用 `i.ytimg.com` 組合）
- 歌單查看（按鈕，ephemeral 回覆）
- `voice_lock` 防止重入式 connect/disconnect
- `requeue_song` 播放失敗時歌曲放回佇列前端（防掉歌）
- voice reconnect 死循環修復（guild.voice_client 認領機制，防止 Already connected 無限 error loop 灌爆 Docker log，2026-04-12）
- DAVE 加密協定支援（davey 0.1.5）
- 非同步歌單載入（不阻塞點歌）

### 音訊品質鏈路

```
YouTube (opus 160kbps, format 251)
  ↓ 串流播放：yt-dlp extract_single → ffmpeg PCM 48kHz → discord.py encoder → DAVE → Discord
  ↓ 快取下載：yt-dlp download (opus copy, 限速 3MB/s) → src/music/cache/{id}.opus
  ↓ 快取播放：本地 opus → ffmpeg PCM 48kHz + volume 正規化 → discord.py encoder → DAVE → Discord
```

### 已知限制

- **DAVE 加密偶爾造成特定區段短暫加速**：discord.py AudioPlayer 的 20ms frame timing 在 DAVE 加密耗時過長時會追趕（`delay = max(0, ...)`），屬於 library 層級問題，非程式碼可解
- **YouTube 來源最高 opus 160kbps**：瀏覽器聽到的差異來自客戶端音效處理，非來源品質差異
- **FFmpegOpusAudio 在 DAVE 下不可用**：會斷續爆音，必須走 FFmpegPCMAudio + discord.py 內建 encoder
- **歌單中的版權/私人影片**：自動跳過並通知，無法繞過

### Config 說明

頻道 ID 存在 `config.json`（與其他頻道設定一致）：
```json
{ "music_voice_channel_id": 1489909579927257130 }
```

歌單存在 `src/settings/music_runtime.json`：
```json
{ "music": { "default_playlist_url": "https://..." } }
```

</details>
