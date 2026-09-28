"""週期活動提醒（深塔／海墟）的純邏輯：推算重置時刻、決定哪些提醒該發、組文案。

不碰 Discord、不碰 DB，方便單元測試；排程迴圈、按鈕與發送在
`commands/periodic_reminder_commands.py`。

每一次重置對應兩則提醒：
- **結束前提醒（ending）**：重置前一天 `ending_reminder_hour` 點發，正常 @，提醒還沒打的人
- **重置提醒（reset）**：重置當下發，靜音 @（有提及紅點、不推播，避免凌晨吵醒人）

bot 離線錯過時的補發時限：ending 補到重置前、reset 補到當天 `reset_catchup_until_hour` 點。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from services.event_time_parser import SERVER_TZ
from sys_settings.periodic_reminder_settings import PeriodicReminderSettings, ReminderCycle

#: StateDB `sent_content` 的 source
SENT_SOURCE = "periodic_reminder"

KIND_ENDING = "ending"
KIND_RESET = "reset"

_WEEKDAYS = "一二三四五六日"


@dataclass(frozen=True)
class Reminder:
    cycle: ReminderCycle
    kind: str
    #: 這則提醒講的是哪一次重置（伺服器時間）
    reset_at: datetime
    send_at: datetime
    #: 過了這個時刻就不補發
    expires_at: datetime

    @property
    def silent(self) -> bool:
        return self.kind == KIND_RESET

    @property
    def dedup_key(self) -> str:
        return f"{self.cycle.key}:{self.reset_at:%Y-%m-%d}:{self.kind}"


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


def reminders_for(cycle: ReminderCycle, reset_at: datetime,
                  settings: PeriodicReminderSettings) -> tuple[Reminder, Reminder]:
    """某一次重置對應的 (結束前提醒, 重置提醒)。"""
    reset_at = reset_at.astimezone(SERVER_TZ)
    ending_at = (reset_at - timedelta(days=1)).replace(
        hour=settings.ending_reminder_hour, minute=0, second=0, microsecond=0)
    catchup_until = reset_at.replace(
        hour=settings.reset_catchup_until_hour, minute=0, second=0, microsecond=0)
    if catchup_until <= reset_at:
        # 重置時刻若晚於補發截止點（例如改成中午後重置），至少給半天補發
        catchup_until = reset_at + timedelta(hours=12)
    ending = Reminder(cycle, KIND_ENDING, reset_at, send_at=ending_at, expires_at=reset_at)
    reset = Reminder(cycle, KIND_RESET, reset_at, send_at=reset_at, expires_at=catchup_until)
    return ending, reset


def _candidates(cycles: Iterable[ReminderCycle], now: datetime,
                settings: PeriodicReminderSettings) -> list[Reminder]:
    """每個項目「最近一次」與「下一次」重置的四則提醒。"""
    result: list[Reminder] = []
    for cycle in cycles:
        for reset_at in (last_reset(cycle, now), next_reset(cycle, now)):
            result.extend(reminders_for(cycle, reset_at, settings))
    return result


def due_reminders(now: datetime, settings: PeriodicReminderSettings) -> list[Reminder]:
    """現在該發（含錯過但還在補發時限內）的提醒，依發送時刻排序。是否已發過由呼叫端查 DB。"""
    due = [r for r in _candidates(settings.cycles, now, settings) if r.send_at <= now < r.expires_at]
    return sorted(due, key=lambda r: r.send_at)


def upcoming_reminders(now: datetime, settings: PeriodicReminderSettings) -> list[Reminder]:
    """還沒到發送時刻的提醒，依時間排序（排程睡多久、啟動 log 用）。"""
    upcoming = [r for r in _candidates(settings.cycles, now, settings) if r.send_at > now]
    return sorted(upcoming, key=lambda r: r.send_at)


# ── 文案 ──

def format_moment(moment: datetime) -> str:
    """10/12（週一）04:00"""
    moment = moment.astimezone(SERVER_TZ)
    return f"{moment.month}/{moment.day}（週{_WEEKDAYS[moment.weekday()]}）{moment:%H:%M}"


def _relative_day(target: datetime, now: datetime) -> Optional[str]:
    days = (target.astimezone(SERVER_TZ).date() - now.astimezone(SERVER_TZ).date()).days
    return {0: "今天", 1: "明天"}.get(days)


def build_reminder_text(reminder: Reminder, role_mention: str, now: datetime) -> str:
    cycle = reminder.cycle
    head = f"{role_mention} {cycle.emoji} **{cycle.name}**"
    if reminder.kind == KIND_ENDING:
        rel = _relative_day(reminder.reset_at, now)
        when = f"{rel} {format_moment(reminder.reset_at)}" if rel else format_moment(reminder.reset_at)
        return f"{head} {when} 重置，這期還沒打完的記得把握時間！"
    ends_at = reminder.reset_at + timedelta(days=cycle.period_days)
    return f"{head} 已重置，新的一期開始了，到 {format_moment(ends_at)} 結束。"


def build_panel_title(settings: PeriodicReminderSettings) -> str:
    return f"🔔 {settings.role_name}"


def build_panel_description(now: datetime, settings: PeriodicReminderSettings) -> str:
    names = "、".join(c.name for c in settings.cycles)
    periods = {c.period_days for c in settings.cycles}
    period_text = f"每 {periods.pop()} 天" if len(periods) == 1 else "定期"
    lines = [
        f"{names}{period_text}重置一次。",
        f"訂閱後，重置前一天 {settings.ending_reminder_hour:02d}:00 會 @ 你；重置當下的提醒不會跳通知。",
        "",
        "**下次重置**",
    ]
    for cycle in sorted(settings.cycles, key=lambda c: next_reset(c, now)):
        lines.append(f"{cycle.emoji} {cycle.name}：{format_moment(next_reset(cycle, now))}")
    return "\n".join(lines)
