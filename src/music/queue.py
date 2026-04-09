from collections import deque
from .models import Song
from .exceptions import QueueEmptyError

class MusicQueue:
    def __init__(self):
        self.main_queue: deque[Song] = deque()      # 原本歌單（循環）
        self.interrupt_queue: deque[Song] = deque() # 插播優先 queue
        self.loop = True                            # 預設循環歌單
        self.current: Song | None = None

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
            return self.interrupt_queue.popleft()
        if self.main_queue:
            song = self.main_queue.popleft()
            if self.loop:
                self.main_queue.append(song)  # 循環放回尾端
            return song
        raise QueueEmptyError("Queue is empty")

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

    def clear_interrupts(self):
        """只清除插播佇列，保留預設歌單"""
        self.interrupt_queue.clear()
        self.current = None

    def clear_all(self):
        """清除所有佇列（含預設歌單）"""
        self.main_queue.clear()
        self.interrupt_queue.clear()
        self.current = None
