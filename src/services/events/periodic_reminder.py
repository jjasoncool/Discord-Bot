"""週期活動提醒（深塔／海墟／終焉矩陣）的純邏輯：推算時刻、決定哪些提醒該發、組文案。

不碰 Discord、不碰 DB，方便單元測試；排程迴圈、按鈕與發送在
`commands/periodic_reminder_commands.py`，版本更新時刻由呼叫端從 `VersionDateResolver` 取得後傳進來。

兩種項目，每個時間點都對應兩則提醒：
- **固定週期（深塔、海墟）**：每 28 天重置。結束前提醒＝重置前一天 `ending_reminder_hour` 點，正常 @；
  重置提醒＝重置當下，靜音 @（有提及紅點、不推播，避免凌晨吵醒人）。
- **跟著版本走（終焉矩陣）**：版本更新維護開始後 7 天 04:00 開放新階段、下一次版本更新時結束。
  結束前提醒＝下一次更新前一天 `ending_reminder_hour` 點；開放提醒＝開放當下，靜音 @。

bot 離線錯過時的補發時限：結束前提醒補到結束前、重置／開放提醒補到當天 `reset_catchup_until_hour` 點。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence, Union

from services.events.event_time_parser import SERVER_TZ
from sys_settings.periodic_reminder_settings import (
    PeriodicReminderSettings,
    ReminderCycle,
    VersionStageItem,
)

#: StateDB `sent_content` 的 source
SENT_SOURCE = "periodic_reminder"

KIND_ENDING = "ending"
KIND_RESET = "reset"

_WEEKDAYS = "一二三四五六日"

Item = Union[ReminderCycle, VersionStageItem]


@dataclass(frozen=True)
class Reminder:
    item: Item
    kind: str
    #: 這則提醒講的時刻：固定週期是重置時刻；矩陣的結束前提醒是版本更新時刻、開放提醒是開放時刻
    reset_at: datetime
    send_at: datetime
    #: 過了這個時刻就不補發
    expires_at: datetime

    @property
    def silent(self) -> bool:
        return self.kind == KIND_RESET

    @property
    def dedup_key(self) -> str:
        return f"{self.item.key}:{self.reset_at:%Y-%m-%d}:{self.kind}"


def _anchor(cycle: ReminderCycle) -> datetime:
    """錨點補上伺服器時區（設定檔裡的 datetime 不帶時區）。"""
    if cycle.anchor.tzinfo is None:
        return cycle.anchor.replace(tzinfo=SERVER_TZ)
    return cycle.anchor.astimezone(SERVER_TZ)


def last_reset(cycle: ReminderCycle, moment: datetime) -> datetime:
    """`moment` 當下或之前最近一次重置。錨點之前的時刻也算得出來。"""
    anchor = _anchor(cycle)
    period = timedelta(days=cycle.period_days)
    return anchor + ((moment - anchor) // period) * period


def next_reset(cycle: ReminderCycle, moment: datetime) -> datetime:
    """`moment` 之後（不含當下）的下一次重置。"""
    return last_reset(cycle, moment) + timedelta(days=cycle.period_days)


def reminders_for(item: Item, reset_at: datetime,
                  settings: PeriodicReminderSettings) -> tuple[Reminder, Reminder]:
    """某一個時刻對應的 (結束前提醒, 重置／開放提醒)。"""
    reset_at = reset_at.astimezone(SERVER_TZ)
    ending_at = (reset_at - timedelta(days=1)).replace(
        hour=settings.ending_reminder_hour, minute=0, second=0, microsecond=0)
    catchup_until = reset_at.replace(
        hour=settings.reset_catchup_until_hour, minute=0, second=0, microsecond=0)
    if catchup_until <= reset_at:
        # 時刻若晚於補發截止點（例如改成中午後重置），至少給半天補發
        catchup_until = reset_at + timedelta(hours=12)
    ending = Reminder(item, KIND_ENDING, reset_at, send_at=ending_at, expires_at=reset_at)
    reset = Reminder(item, KIND_RESET, reset_at, send_at=reset_at, expires_at=catchup_until)
    return ending, reset


def _split(update_starts: Sequence[datetime], now: datetime) -> tuple[list[datetime], list[datetime]]:
    starts = sorted(u.astimezone(SERVER_TZ) for u in update_starts)
    return [u for u in starts if u <= now], [u for u in starts if u > now]


def stage_open_at(stage: VersionStageItem, update_start: datetime) -> datetime:
    """某次版本更新對應的階段開放時刻：維護開始日 +N 天的 04:00。"""
    return (update_start + timedelta(days=stage.open_delay_days)).replace(
        hour=4, minute=0, second=0, microsecond=0)


def _stage_candidates(stage: VersionStageItem, now: datetime, update_starts: Sequence[datetime],
                      settings: PeriodicReminderSettings) -> list[Reminder]:
    """最近一次與下一次（已知的）版本更新：各自的「本階段結束前提醒」與「新階段開放提醒」。"""
    past, future = _split(update_starts, now)
    result: list[Reminder] = []
    for update in past[-1:] + future[:1]:
        ending, _ = reminders_for(stage, update, settings)
        _, opening = reminders_for(stage, stage_open_at(stage, update), settings)
        result.extend((ending, opening))
    return result


def _candidates(now: datetime, settings: PeriodicReminderSettings,
                update_starts: Sequence[datetime]) -> list[Reminder]:
    result: list[Reminder] = []
    for cycle in settings.cycles:
        for reset_at in (last_reset(cycle, now), next_reset(cycle, now)):
            result.extend(reminders_for(cycle, reset_at, settings))
    for stage in settings.version_stages:
        result.extend(_stage_candidates(stage, now, update_starts, settings))
    return result


def due_reminders(now: datetime, settings: PeriodicReminderSettings,
                  update_starts: Sequence[datetime] = ()) -> list[Reminder]:
    """現在該發（含錯過但還在補發時限內）的提醒，依發送時刻排序。是否已發過由呼叫端查 DB。"""
    due = [r for r in _candidates(now, settings, update_starts) if r.send_at <= now < r.expires_at]
    return sorted(due, key=lambda r: r.send_at)


def upcoming_reminders(now: datetime, settings: PeriodicReminderSettings,
                       update_starts: Sequence[datetime] = ()) -> list[Reminder]:
    """還沒到發送時刻的提醒，依時間排序（排程睡多久、啟動 log 用）。"""
    upcoming = [r for r in _candidates(now, settings, update_starts) if r.send_at > now]
    return sorted(upcoming, key=lambda r: r.send_at)


# ── 文案 ──

def format_moment(moment: datetime) -> str:
    """10/12（週一）04:00"""
    moment = moment.astimezone(SERVER_TZ)
    return f"{moment.month}/{moment.day}（週{_WEEKDAYS[moment.weekday()]}）{moment:%H:%M}"


def _relative_day(target: datetime, now: datetime) -> Optional[str]:
    days = (target.astimezone(SERVER_TZ).date() - now.astimezone(SERVER_TZ).date()).days
    return {0: "今天", 1: "明天"}.get(days)


def _when(target: datetime, now: datetime) -> str:
    rel = _relative_day(target, now)
    return f"{rel} {format_moment(target)}" if rel else format_moment(target)


def build_reminder_text(reminder: Reminder, role_mention: str, now: datetime) -> str:
    item = reminder.item
    head = f"{role_mention} {item.emoji} **{item.name}**"
    if isinstance(item, VersionStageItem):
        if reminder.kind == KIND_ENDING:
            return f"{head} 本階段將在{_when(reminder.reset_at, now)} 隨版本更新結束，還沒打完的記得把握時間！"
        return f"{head} 新階段開放了，到下次版本更新前結束。"
    if reminder.kind == KIND_ENDING:
        return f"{head} {_when(reminder.reset_at, now)} 重置，這期還沒打完的記得把握時間！"
    ends_at = reminder.reset_at + timedelta(days=item.period_days)
    return f"{head} 已重置，新的一期開始了，到 {format_moment(ends_at)} 結束。"


def stage_panel_line(stage: VersionStageItem, now: datetime, update_starts: Sequence[datetime]) -> str:
    """面板上矩陣那一行：空窗週顯示開放時刻；開放中且已知下一次更新就顯示結束時刻，未知就寫「於版本末結束」。"""
    past, future = _split(update_starts, now)
    head = f"{stage.emoji} {stage.name}："
    if past and now < stage_open_at(stage, past[-1]):
        return f"{head}新階段 {format_moment(stage_open_at(stage, past[-1]))} 開放"
    if future:
        return f"{head}本階段開放中，{format_moment(future[0])} 結束"
    return f"{head}本階段開放中，於版本末結束"


def build_panel_title(settings: PeriodicReminderSettings) -> str:
    return f"🔔 {settings.role_name}"


def build_panel_description(now: datetime, settings: PeriodicReminderSettings,
                            update_starts: Sequence[datetime] = ()) -> str:
    rules = []
    if settings.cycles:
        names = "、".join(c.name for c in settings.cycles)
        periods = {c.period_days for c in settings.cycles}
        rules.append(f"{names}每 {periods.pop()} 天重置" if len(periods) == 1 else f"{names}定期重置")
    for stage in settings.version_stages:
        rules.append(f"{stage.name}在版本更新 {stage.open_delay_days} 天後開放新階段")
    lines = [
        "；".join(rules) + "。",
        f"訂閱後，重置或結束前一天 {settings.ending_reminder_hour:02d}:00 會 @ 你；重置與開放當下的提醒不會跳通知。",
        "",
        "**時程**",
    ]
    for cycle in sorted(settings.cycles, key=lambda c: next_reset(c, now)):
        lines.append(f"{cycle.emoji} {cycle.name}：{format_moment(next_reset(cycle, now))} 重置")
    for stage in settings.version_stages:
        lines.append(stage_panel_line(stage, now, update_starts))
    return "\n".join(lines)
