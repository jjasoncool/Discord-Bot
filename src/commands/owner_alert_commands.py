"""群主通知與管理主控台：要人介入的狀況私訊群主、底下一顆「重新偵測」；「機器人狀態」列各種狀況；群主私訊 bot 就拿到管理選單。

架構定位：介面層（commands）的 cog。
  上層：`discord_bot` 的 COMMAND_MODULES 載入；`management_commands` 的「機器人狀態」按鈕呼叫 `show_status`。
  下層：`utils.owner_alerts`（警報與登記表）、`utils.dm_notifier`（私訊）、`utils.discord_members`（群主、權限）、
  `llm.client.lemonade_admin`／`services.llm_service`（Lemonade 的重測）、`llm.storage.ai_interactions_store`
  （重測成功後回填向量）、`bot.telegram_relay_worker`（叫醒補判）、`commands.management_commands`（管理選單）。

介面：
- `OwnerAlertCommands.show_status(interaction)`：回「機器人狀態」（伺服器裡只有本人看得到；私訊裡一般訊息）。
- `OwnerAlertCommands.handle_retest(interaction, kind, key)`：按鈕按下：重測、把結果回寫在同一則訊息上。
- `OwnerAlertCommands.check_backend_restarts()`：每分鐘一次：自癒放棄中的模型行程換了（群主重啟了 Lemonade）就自動重新偵測、私訊結果。
- `RetestButton`／`StatusRefreshButton`：DynamicItem，custom_id `owner:retest:<kind>:<key>`、`owner:status:refresh`，重啟後照樣能按。
- 私訊 listener：群主在私訊裡傳任何一句話，回管理選單（和 /server_manager 同一份）。

規則：
- 按鈕、狀態、私訊入口只有群主能用（`_ACCESS`／`_is_console_user`）；要放寬到管理員只改那兩處。
- 各種狀況的重測在 `cog_load` 登記：要碰 bot 的東西（轉發 worker）才放這裡，純後端的探測在 `LLMService.probe`／`probe_backend`。
- 通知文案由發警報的那層寫；這裡只加時間、結果那一行（訊息太長時保留最新那行、截掉前面的）。
- Lemonade 自癒只在 bot 這個行程做：`cog_load` 打開（`lemonade_admin.allow_heal`）、`cog_unload` 關掉——有人收通知、
  有重新偵測、有重開偵測的地方才自癒。

例外與決策：
- 私訊不存聊天、不插話：`discord_bot.on_message` 一開始就把私訊擋掉，只有這裡的 listener 看私訊。
- 解除時回寫原本那則私訊（補一行「已恢復」、按鈕停用）；訊息與最後寫上去的文字記在記憶體，重啟就忘——重啟後舊訊息上的按鈕還是能按。
- 通知一則一則依序送（同一把先「壞了」後「好了」時，回寫才找得到前一則）。
- 從「機器人狀態」按重測：結果寫在面板最上面、整個面板重畫（各項目與重新整理都還在）；從警報私訊按：補在那則底下。
- Lemonade 的重測：群主按的（`retest_lemonade`）先清全部自癒紀錄，向量、聊天兩顆主模型都測，按的是別顆（例如 reranker）
  就再單獨測那顆；各自照自己的結果解除自己的警報，回報照按的那顆。回填向量只看向量模型、叫醒 Telegram 補判只看聊天模型。
- 自動重測（`check_backend_restarts`）不清紀錄：放棄中的模型行程換了才探測一輪，確認好了才只放那幾顆（`release`），
  還是壞就當新的一輪重發警報（不吃一小時去重），群主才知道重啟沒解決；顯示卡被佔著沒測到就下一分鐘再試，不當成壞。
  偵測只在有模型放棄時才打 health。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Optional

import discord
from discord.ext import commands

from llm.client import lemonade_admin
from services.llm_service import LLMService, ProbeResult
from sys_settings.time_settings import APP_TZ
from utils import owner_alerts
from utils.background_tasks import periodic, spawn, supervise
from utils.discord_members import bot_owner_id, require_access, resolve_user
from utils.dm_notifier import send_dm
from utils.owner_alerts import Alert, RetestResult
from utils.utils import safe_send_interaction_message

logger = logging.getLogger(__name__)

RETEST_TEMPLATE = r"owner:retest:(?P<kind>[a-z0-9_]+):(?P<key>[A-Za-z0-9._*\-]+)"
STATUS_REFRESH_ID = "owner:status:refresh"
#: 誰能按；要放寬到管理員只改這裡（私訊裡只放得了群主）
_ACCESS = dict(owner_only=True, allow_dm=True)
_NOT_LOADED = "狀態功能目前沒有在運作，請看 log。"
#: 自癒放棄期間多久看一次模型行程換了沒（群主重啟 Lemonade 後自動重測）
_RESTART_CHECK_SECONDS = 60
#: Discord 一則訊息的長度上限（留一點餘裕）
_MESSAGE_MAX = 1900


def _stamp() -> str:
    return datetime.now(APP_TZ).strftime("%H:%M")


def _probe_text(label: str, probe: ProbeResult) -> str:
    if probe.ok:
        return f"{label} {probe.seconds:.1f} 秒"
    return f"{label}{'沒測到' if probe.busy else '失敗'}（{probe.detail}）"


def _append_line(content: str, line: str) -> str:
    """在訊息底下補一行；太長時截掉前面的舊內容，最新那行一定看得到（同一則重測好幾次會一直變長）。"""
    line = line[:_MESSAGE_MAX]
    room = _MESSAGE_MAX - len(line) - 1
    if room <= 0:
        return line
    if len(content) > room:
        content = "…" + content[-(room - 1):] if room > 1 else ""
    return f"{content}\n{line}" if content else line


def _view(*items: discord.ui.Item) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for item in items:
        view.add_item(item)
    return view


def _cog(interaction: discord.Interaction) -> Optional["OwnerAlertCommands"]:
    return interaction.client.get_cog("OwnerAlertCommands")


class RetestButton(discord.ui.DynamicItem[discord.ui.Button], template=RETEST_TEMPLATE):
    """「重新偵測」：custom_id 帶狀況種類與那一把的 key。"""

    def __init__(self, kind: str, key: str, *, label: str = "重新偵測", disabled: bool = False,
                 style: discord.ButtonStyle = discord.ButtonStyle.primary):
        super().__init__(discord.ui.Button(label=label, emoji="🔄" if not disabled else "✅", style=style,
                                           custom_id=f"owner:retest:{kind}:{owner_alerts.clean_key(key)}", disabled=disabled))
        self.kind = kind
        self.key = owner_alerts.clean_key(key)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["kind"], match["key"], label=item.label or "重新偵測", disabled=item.disabled, style=item.style)

    async def callback(self, interaction: discord.Interaction):
        cog = _cog(interaction)
        if cog is None:
            await safe_send_interaction_message(interaction, _NOT_LOADED, ephemeral=True)
            return
        await cog.handle_retest(interaction, self.kind, self.key)


class StatusRefreshButton(discord.ui.DynamicItem[discord.ui.Button], template=STATUS_REFRESH_ID):
    """「機器人狀態」的重新整理：同一則訊息換內容。"""

    def __init__(self):
        super().__init__(discord.ui.Button(label="重新整理", style=discord.ButtonStyle.secondary, custom_id=STATUS_REFRESH_ID))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        cog = _cog(interaction)
        if cog is None:
            await safe_send_interaction_message(interaction, _NOT_LOADED, ephemeral=True)
            return
        if not await require_access(interaction, **_ACCESS):
            return
        embed, view = await cog.status_message()
        await interaction.response.edit_message(embed=embed, view=view)


class OwnerAlertCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        #: 警報那則私訊與它現在的文字（解除時回寫）；重啟就忘
        self._messages: dict[tuple[str, str], tuple[discord.Message, str]] = {}
        self._llm: Optional[LLMService] = None
        #: 通知一則一則送：同一把先壞後好時，「好了」要在「壞了」那則存起來之後才回寫得到
        self._deliver_lock = asyncio.Lock()
        self._restart_watch: Optional[asyncio.Task] = None
        #: 自動重測時顯示卡被佔著、沒測到的模型：下一分鐘再測
        self._recheck: set[str] = set()

    async def cog_load(self):
        self.bot.add_dynamic_items(RetestButton, StatusRefreshButton)
        owner_alerts.register(lemonade_admin.ALERT_KIND, title="模型後端（Lemonade）",
                              retest=self.retest_lemonade, status=self.lemonade_status)
        owner_alerts.register("owner_id", title="群主通知", status=self.owner_status)
        owner_alerts.set_listener(self._on_alert_threadsafe)
        lemonade_admin.allow_heal(True)
        self._restart_watch = supervise(
            lambda: periodic(_RESTART_CHECK_SECONDS, self.check_backend_restarts, name="Lemonade 重開偵測"),
            name="Lemonade 重開偵測",
        )
        if not bot_owner_id():
            logger.warning("OWNER_ID 沒設定：要人介入的狀況沒人收得到私訊，管理主控台也沒人能用")

    async def cog_unload(self):
        if self._restart_watch is not None:
            self._restart_watch.cancel()
            self._restart_watch = None
        lemonade_admin.allow_heal(False)
        owner_alerts.set_listener(None)
        self.bot.remove_dynamic_items(RetestButton, StatusRefreshButton)

    # ---------- 通知 ----------

    def _on_alert_threadsafe(self, alert: Alert) -> None:
        """警報可能從算 embedding 的執行緒發出：排回 event loop 再送私訊。"""
        self.bot.loop.call_soon_threadsafe(lambda: spawn(self.deliver(alert), name="群主通知"))

    async def deliver(self, alert: Alert) -> Optional[discord.Message]:
        """把一則警報變成私訊：要人介入的掛「重新偵測」按鈕；一行通知順便把舊警報那則標成已恢復。"""
        owner_id = bot_owner_id()
        if not owner_id:
            logger.warning("OWNER_ID 沒設定，這則群主通知沒送：%s", alert.text[:200])
            return None
        async with self._deliver_lock:
            user = await resolve_user(self.bot, owner_id)
            if alert.severity == "info":
                await self._mark_resolved(alert.kind, alert.key)
                return await send_dm(user, content=alert.text[:1900])
            text = alert.text[:_MESSAGE_MAX]
            message = await send_dm(user, content=text, view=_view(RetestButton(alert.kind, alert.key)))
            if message is not None:
                # 同一把又送了一則（升級成要人處理、重啟後還是壞）：舊那則收掉，按鈕只留在最新那則
                await self._close_message(alert.kind, alert.key, "🔁", "狀況有更新，見下一則", "見下一則",
                                          discord.ButtonStyle.secondary)
                self._messages[(alert.kind, alert.key)] = (message, text)
            return message

    async def _mark_resolved(self, kind: str, key: str, *, note: str = "已恢復") -> None:
        """警報解除：原本那則私訊補一行、按鈕停用。"""
        await self._close_message(kind, key, "✅", note, "已恢復", discord.ButtonStyle.success)

    async def _close_message(self, kind: str, key: str, icon: str, note: str, label: str,
                             style: discord.ButtonStyle) -> None:
        """把記著的那則警報私訊收尾：補一行、按鈕換成停用的 `label`；沒記著就不做。"""
        entry = self._messages.pop((kind, key), None)
        if entry is None:
            return
        message, content = entry
        try:
            await message.edit(content=_append_line(content, f"{icon} {_stamp()} {note}"),
                               view=_view(RetestButton(kind, key, label=label, disabled=True, style=style)))
        except discord.HTTPException as exc:
            logger.warning("回寫警報私訊失敗（%s/%s）：%s", kind, key, exc)

    # ---------- 按鈕 ----------

    async def handle_retest(self, interaction: discord.Interaction, kind: str, key: str) -> None:
        """按「重新偵測」：跑登記的重測，把結果寫回按的那則訊息。

        警報私訊：先把按鈕換成「偵測中」，結果補在底下，成功就停用按鈕、失敗按鈕留著。
        「機器人狀態」面板（有 embed 的那種）：結果寫在最上面、整個面板重畫，各項目的按鈕與重新整理都還在。
        """
        if not await require_access(interaction, **_ACCESS):
            return
        message = interaction.message
        on_panel = bool(getattr(message, "embeds", None))
        original = (getattr(message, "content", "") or "")
        if on_panel:
            await interaction.response.defer()
        else:
            await interaction.response.edit_message(
                content=original, view=_view(RetestButton(kind, key, label="偵測中…", disabled=True)))
        before = {(a.kind, a.key) for a in owner_alerts.active()}
        try:
            result = await owner_alerts.retest(kind, key)
        except Exception as exc:
            # 互動的邊界：重測函式出錯也要把按鈕還回去，不能停在「偵測中」
            logger.error("重測 %s/%s 出錯：%s", kind, key, exc, exc_info=True)
            result = RetestResult(False, f"重測出錯：{type(exc).__name__}: {exc}"[:300])
        after = {(a.kind, a.key) for a in owner_alerts.active()}
        icon, verdict = ("✅", "正常") if result.ok else ("⏳", "這次沒測到") if result.untested else ("❌", "還是壞")
        line = f"{icon} {_stamp()} 重新偵測：{verdict}" + (f"——{result.text}" if result.text else "")
        try:
            if on_panel:
                embed, view = await self.status_message()
                await interaction.edit_original_response(content=line[:_MESSAGE_MAX], embed=embed, view=view)
            else:
                content = _append_line(original, line)
                button = (RetestButton(kind, key, label="已恢復", disabled=True, style=discord.ButtonStyle.success)
                          if result.ok else RetestButton(kind, key))
                await interaction.edit_original_response(content=content, view=_view(button))
                if result.ok:
                    self._messages.pop((kind, key), None)
                elif message is not None:
                    # 失敗的那則還要留著：之後後端自己好了（inform）要回寫它
                    self._messages[(kind, key)] = (message, content)
        except discord.HTTPException as exc:
            logger.warning("回寫重測結果失敗（%s/%s）：%s", kind, key, exc)
        # 這次重測解除的警報（含從面板按的那一把、順便解除的另一顆模型），它們的私訊都標成已恢復
        for pair in before - after:
            await self._mark_resolved(*pair)

    # ---------- 狀態 ----------

    async def status_message(self) -> tuple[discord.Embed, discord.ui.View]:
        """「機器人狀態」：登記過的每種狀況一行（紅＝要你處理、綠＝正常），有重測的掛一顆按鈕。"""
        alerts = owner_alerts.active()
        lines: list[str] = []
        view = _view()
        for spec in owner_alerts.kinds():
            mine = [a for a in alerts if a.kind == spec.kind]
            status = await owner_alerts.status_line(spec.kind)
            lines.append(f"{'🔴' if mine else '🟢'} **{spec.title}**　{status or ('要你處理' if mine else '正常')}")
            for alert in mine:
                lines.append(f"-# {alert.text[:300]}")
            if spec.retest is not None:
                view.add_item(RetestButton(spec.kind, mine[0].key if mine else "*", label=f"重測 {spec.title}"[:80]))
        view.add_item(StatusRefreshButton())
        embed = discord.Embed(
            title="機器人狀態", description="\n".join(lines) or "（還沒有登記任何狀況）",
            color=discord.Color.red() if alerts else discord.Color.green(),
        )
        embed.set_footer(text=f"{_stamp()} 更新 · 紅＝要你處理、綠＝正常；按下面的按鈕會重測那一項")
        return embed, view

    async def show_status(self, interaction: discord.Interaction) -> None:
        if not await require_access(interaction, **_ACCESS):
            return
        embed, view = await self.status_message()
        await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=interaction.guild is not None)

    def owner_status(self) -> str:
        return "OWNER_ID 已設定" if bot_owner_id() else "OWNER_ID 沒設定：通知送不出去、主控台沒人能用"

    async def lemonade_status(self) -> str:
        # 看紀錄要拿 lemonade_admin 的鎖，別的執行緒正在載入模型時不能卡住 event loop
        return await asyncio.to_thread(lemonade_admin.heal_summary)

    # ---------- Lemonade 的重測 ----------

    def _llm_service(self) -> LLMService:
        if self._llm is None:
            self._llm = LLMService()
        return self._llm

    async def retest_lemonade(self, key: str) -> RetestResult:
        """群主按的重新偵測：清掉全部自癒紀錄與載入快取（Lemonade 修好、重啟後才會再救、再推載入選項），再探測
        （`_probe_lemonade`，按的是主模型以外的那顆也一起測）。回報的成敗看按的那一把；面板上沒有警報時按的（key＝*）看全部。"""
        await asyncio.to_thread(lemonade_admin.reset_cache)
        results, parts = await self._probe_lemonade(extra=[key])
        mine = results.get(owner_alerts.clean_key(key))
        judged = [mine] if mine is not None else list(results.values())
        failed = [probe for probe in judged if not probe.ok]
        return RetestResult(not failed, "；".join(parts), untested=bool(failed) and all(p.busy for p in failed))

    async def check_backend_restarts(self) -> None:
        """自癒放棄中的模型，行程換了（群主重啟了 Lemonade 或手動重載）就自動探測一輪、私訊結果（不清別顆的紀錄）：
        好了用一行通知（順便把舊警報那則標成已恢復）；還是壞就當新的一輪重發警報，群主才知道重啟沒解決；
        顯示卡被佔著沒測到就下一分鐘再測。"""
        replaced = set(await asyncio.to_thread(self._llm_service().replaced_backends)) | self._recheck
        self._recheck = set()
        if not replaced:
            return
        results, parts = await self._probe_lemonade(extra=sorted(replaced))
        summary = "；".join(parts)
        kind = lemonade_admin.ALERT_KIND
        for model in sorted(replaced):
            probe = results.get(owner_alerts.clean_key(model))
            head = f"🔄 偵測到 {model} 的行程換了（Lemonade 重啟或重新載入過），自動重新偵測："
            if probe is None or probe.busy:
                self._recheck.add(model)
                continue
            if probe.ok:
                owner_alerts.inform(kind, model, f"{head}正常——{summary}")
            else:
                owner_alerts.resolve(kind, model)   # 新的一輪：一小時去重不擋這則
                owner_alerts.emit(kind, model, f"{head}還是壞——{summary}。bot 不會再自動重開它，請檢查那張卡或驅動"
                                               "（可能要重開機），修好後按「重新偵測」。")

    async def _probe_lemonade(self, *, extra: Iterable[str] = ()) -> tuple[dict[str, ProbeResult], list[str]]:
        """向量、聊天兩顆主模型各真的算一次，`extra` 裡別的模型再單獨測；回 {模型的警報 key: 結果} 與每顆一行說明。
        測過能算的：解除它的警報、放掉它的自癒紀錄（`release`：還在「放棄」裡的話，之後壞了才會再救）。
        向量模型好了就背景回填沒有向量的互動紀錄，聊天模型好了就叫醒 Telegram 過濾補判。"""
        llm = self._llm_service()
        embed = await llm.probe(embedding=True)
        chat = await llm.probe(embedding=False)
        results = {owner_alerts.clean_key(embed.model): embed, owner_alerts.clean_key(chat.model): chat}
        parts = [_probe_text("向量模型", embed), _probe_text("聊天模型", chat)]
        for model in extra:
            key = owner_alerts.clean_key(model)
            if key == "*" or key in results:
                continue
            results[key] = other = await llm.probe_backend(model)
            parts.append(_probe_text(model, other))
        healthy = [probe.model for probe in results.values() if probe.ok]
        if healthy:
            await asyncio.to_thread(lemonade_admin.release, healthy)
        for alert in owner_alerts.active():
            probe = results.get(alert.key)
            if alert.kind == lemonade_admin.ALERT_KIND and probe is not None and probe.ok:
                owner_alerts.resolve(alert.kind, alert.key)
                await self._mark_resolved(alert.kind, alert.key)   # 它的私訊也收尾（包括這一輪探測途中發的）
        if embed.ok:
            from llm.storage.ai_interactions_store import backfill_embeddings
            spawn(asyncio.to_thread(backfill_embeddings), name="ai_interactions 向量回填")
            parts.append("已開始回填沒有向量的互動紀錄")
        worker = getattr(self.bot, "telegram_relay_worker", None)
        if chat.ok and worker is not None and getattr(worker, "running", False):
            worker.wake_recheck()
            parts.append("已叫醒 Telegram 過濾補判")
        return results, parts

    # ---------- 私訊入口 ----------

    def _is_console_user(self, user) -> bool:
        """誰能從私訊叫出管理選單；要放寬到管理員只改這裡（要回伺服器查成員）。"""
        owner_id = bot_owner_id()
        return bool(owner_id) and getattr(user, "id", None) == owner_id

    @commands.Cog.listener("on_message")
    async def on_dm(self, message: discord.Message) -> None:
        if message.guild is not None or message.author.bot or not self._is_console_user(message.author):
            return
        manager = self.bot.get_cog("ManagementCommands")
        if manager is None:
            await message.channel.send("管理指令模組沒有載入，請看 log。")
            return
        embed, view = manager.manager_menu()
        await message.channel.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(OwnerAlertCommands(bot))
