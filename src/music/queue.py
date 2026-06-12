import random
from collections import deque
from .models import Song
from .exceptions import QueueEmptyError

class MusicQueue:
    def __init__(self):
        self.main_queue: deque[Song] = deque()      # 原本歌單（循環）
        self.interrupt_queue: deque[Song] = deque() # 插播優先 queue
        self.loop = True                            # 預設循環歌單
        self._shuffle = False                       # 隨機播放
        self.current: Song | None = None
        self._next_shuffle: Song | None = None      # shuffle 模式下預先決定的下一首

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, value: bool):
        self._shuffle = value
        if value and self.main_queue:
            # 開啟時立刻決定下一首
            self._next_shuffle = random.choice(self.main_queue)
        else:
            self._next_shuffle = None

    def add_to_main(self, songs: list[Song]):
        self.main_queue.extend(songs)

    def add_interrupt(self, song: Song):
        """插播：優先播放，播完才切回主歌單"""
        self.interrupt_queue.append(song)

    def add_interrupt_front(self, song: Song):
        """將插播歌曲放回佇列最前面，供失敗重試用"""
        self.interrupt_queue.appendleft(song)

    def add_main_front(self, song: Song):
        """將主歌單歌曲放回佇列最前面，供失敗重試用"""
        self.main_queue.appendleft(song)

    def get_next(self) -> Song:
        if self.interrupt_queue:
            self._next_shuffle = None  # 插播結束後重新隨機
            return self.interrupt_queue.popleft()
        if self.main_queue:
            if self.shuffle:
                # 用預先決定的下一首，或隨機取
                if self._next_shuffle and self._next_shuffle in self.main_queue:
                    song = self._next_shuffle
                    self.main_queue.remove(song)
                else:
                    index = random.randint(0, len(self.main_queue) - 1)
                    song = self.main_queue[index]
                    del self.main_queue[index]
                # 預先決定下一首（供 prefetch 使用）
                if self.main_queue:
                    self._next_shuffle = random.choice(self.main_queue)
                else:
                    self._next_shuffle = song if self.loop else None
            else:
                song = self.main_queue.popleft()
                self._next_shuffle = None
            # NOTE: 不在此處 append 回主歌單，否則 play() 失敗 + requeue 會造成
            # 同一首同時出現於 deque 前後端，每次 retry 淨增 1 首。
            # 由 player 在 play() 成功後呼叫 mark_played 完成 loop append。
            return song
        raise QueueEmptyError("Queue is empty")

    def mark_played(self, song: Song, is_interrupt: bool):
        """play() 成功送出後呼叫；loop 模式下將主歌單歌曲附回尾端"""
        if is_interrupt:
            return
        if self.loop:
            self.main_queue.append(song)

    def peek_next(self) -> Song | None:
        """查看下一首要播的歌（不取出），供 prefetch 使用"""
        if self.interrupt_queue:
            return self.interrupt_queue[0]
        if self.main_queue:
            if self.shuffle and self._next_shuffle:
                return self._next_shuffle
            return self.main_queue[0]
        return None

    def requeue_song(self, song: Song, is_interrupt: bool):
        """將歌曲放回對應佇列前端，避免播放失敗時掉歌"""
        if is_interrupt:
            self.add_interrupt_front(song)
        else:
            self.add_main_front(song)

    def remove_song(self, song: Song):
        """從主歌單中徹底移除（不再循環播放）"""
        try:
            self.main_queue.remove(song)
        except ValueError:
            pass

    def is_interrupt_active(self) -> bool:
        return len(self.interrupt_queue) > 0

    def remove_interrupts_by(self, user_id: int) -> int:
        """移除指定使用者點的、尚未播放的插播歌，回傳移除數量"""
        if not self.interrupt_queue:
            return 0
        before = len(self.interrupt_queue)
        self.interrupt_queue = deque(
            s for s in self.interrupt_queue if s.requested_by_id != user_id
        )
        return before - len(self.interrupt_queue)

    def clear_all(self):
        """清除所有佇列（含預設歌單）"""
        self.main_queue.clear()
        self.interrupt_queue.clear()
        self.current = None
