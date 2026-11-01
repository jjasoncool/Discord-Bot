"""群主通知：要人介入的狀況私訊群主、底下一顆「重新偵測」；登記模型後端那項的重測與狀態；「機器人狀態」面板本體在 `admin_status`。

架構定位：介面層（commands）的 cog。
  上層：`discord_bot` 的 COMMAND_MODULES 載入；主控台的「機器人狀態」直接畫 `admin_status.render_status`，重測按鈕才回到這裡；
  `admin_status` 的面板按鈕呼叫 `handle_retest`、`close_resolved_dms`。
  下層：`utils.owner_alerts`（警報與登記表）、`commands.admin_status`（面板、其餘八項的登記）、`utils.dm_notifier`（私訊）、
  `utils.discord_members`（群主、權限）、`llm.client.lemonade_admin`／`services.llm_service`（Lemonade 的重測）、
  `llm.storage.ai_interactions_store`（重測成功後回填向量）、`bot.telegram_relay_worker`（叫醒補判）。

介面：
- `OwnerAlertCommands.handle_retest(interaction, kind, key, panel_expanded=None)`：按鈕按下：重測、把結果回寫在同一則訊息上
  （`panel_expanded` 有給＝從面板按的，面板整個重畫）。
- `OwnerAlertCommands.close_resolved_dms()`：把已解除的警報的私訊都標成已恢復（面板全部重測後呼叫）。
- `OwnerAlertCommands.probe_lemonade()`：只探測不清紀錄（面板「全部重測」用；那一列自己的「重測」才清自癒紀錄）。
- `OwnerAlertCommands.check_backend_restarts()`：每分鐘一次：自癒放棄中的模型行程換了（群主重啟了 Lemonade）就自動重新偵測、私訊結果。
- `RetestButton`：DynamicItem，custom_id `owner:retest:<kind>:<key>`，警報私訊上那顆，重啟後照樣能按。

規則：
- 按鈕只有群主能用（`_ACCESS`）；要放寬到管理員只改那一行。
- 各種狀況的重測在 `cog_load` 登記：模型後端在這裡（要碰 bot 的東西：轉發 worker），其餘八項在 `admin_status.register_kinds`；
  純後端的探測在 `LLMService.probe`／`probe_backend`。
- 通知文案由發警報的那層寫；這裡只加時間、結果那一行（訊息太長時保留最新那行、截掉前面的）。
- Lemonade 自癒只在 bot 這個行程做：`cog_load` 打開（`lemonade_admin.allow_heal`）、`cog_unload` 關掉——有人收通知、
  有重新偵測、有重開偵測的地方才自癒。

例外與決策：
- 私訊裡的文字不回：管理主控台只由 /server_manager 叫出來（私訊的對話留給之後的 AI 私聊）。
- 解除時回寫原本那則私訊（補一行「已恢復」、按鈕停用）；訊息與最後寫上去的文字記在記憶體，重啟就忘——重啟後舊訊息上的按鈕還是能按。
- 通知一則一則依序送（同一把先「壞了」後「好了」時，回寫才找得到前一則）。
- 從「機器人狀態」按重測：結果寫在面板最上面、整個面板重畫（各項目與按鈕都還在）；從警報私訊按：補在那則底下。
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

from commands import admin_status
from llm.client import lemonade_admin
from services.llm_service import LLMService, ProbeResult
from sys_settings.time_settings import APP_TZ
from utils import owner_alerts
from utils.background_tasks import periodic, spawn, supervise
from utils.discord_members import bot_owner_id, require_access, resolve_user
from utils.discord_content import edit_screen
from utils.dm_notifier import send_dm
from utils.owner_alerts import Alert, RetestResult, Status
from utils.utils import safe_send_interaction_message

logger = logging.getLogger(__name__)

RETEST_TEMPLATE = r"owner:retest:(?P<kind>[a-z0-9_]+):(?P<key>[A-Za-z0-9._*\-]+)"
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
        self.bot.add_dynamic_items(RetestButton, *admin_status.DYNAMIC_ITEMS)
        owner_alerts.register(lemonade_admin.ALERT_KIND, title="模型後端（Lemonade）",
                              retest=self.retest_lemonade, status=self.lemonade_status)
        admin_status.register_kinds(self.bot)
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
        self.bot.remove_dynamic_items(RetestButton, *admin_status.DYNAMIC_ITEMS)

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

    async def handle_retest(self, interaction: discord.Interaction, kind: str, key: str, *,
                            panel_expanded: Optional[bool] = None) -> None:
        """按「重新偵測」：跑登記的重測，把結果寫回按的那則訊息。

        警報私訊：先把按鈕換成「偵測中」，結果補在底下，成功就停用按鈕、失敗按鈕留著。
        「機器人狀態」面板（`panel_expanded` 有給）：結果寫在最上面、整個面板重畫，各項目的按鈕都還在。
        """
        if not await require_access(interaction, **_ACCESS):
            return
        message = interaction.message
        if panel_expanded is None and getattr(message, "embeds", None) \
                and not getattr(getattr(message, "flags", None), "components_v2", False):
            panel_expanded = False      # 舊版（embed）狀態面板上的重測按鈕：當面板處理，重畫成新版版面
        on_panel = panel_expanded is not None
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
                await edit_screen(interaction, view=await admin_status.render_status(expanded=bool(panel_expanded), headline=line))
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

    async def close_resolved_dms(self) -> None:
        """已經不在警報裡、但私訊還開著的，都標成已恢復（面板全部重測後）。"""
        still = {(a.kind, a.key) for a in owner_alerts.active()}
        for pair in [pair for pair in self._messages if pair not in still]:
            await self._mark_resolved(*pair)

    async def lemonade_status(self) -> Status:
        # 看紀錄要拿 lemonade_admin 的鎖，別的執行緒正在載入模型時不能卡住 event loop
        gave_up, restarted = await asyncio.to_thread(lemonade_admin.heal_state)
        text = await asyncio.to_thread(lemonade_admin.heal_summary)
        level = "alert" if gave_up else "watch" if restarted else "ok"
        return Status(level, text)

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

    async def probe_lemonade(self, key: str = "*") -> RetestResult:
        """只探測、不清紀錄（面板「全部重測」用）：兩顆主模型各算一次，能算的照舊解除自己的警報。"""
        results, parts = await self._probe_lemonade()
        failed = [probe for probe in results.values() if not probe.ok]
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


async def setup(bot):
    await bot.add_cog(OwnerAlertCommands(bot))
