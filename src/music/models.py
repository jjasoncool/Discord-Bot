from dataclasses import dataclass
from typing import Optional

@dataclass
class Song:
    title: str
    url: str
    webpage_url: str
    duration: int
    thumbnail: Optional[str] = None

    @classmethod
    def from_info(cls, info: dict):
        return cls(
            title=info.get("title", "Unknown Title"),
            url=info["url"],                    # 串流 URL
            webpage_url=info.get("webpage_url", ""),
            duration=int(info.get("duration", 0)),
            thumbnail=info.get("thumbnail"),
        )
