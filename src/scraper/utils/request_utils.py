"""request 相關共用工具"""
import random
import time
from typing import Optional


def human_sleep(a: Optional[float] = None, b: Optional[float] = None):
    """模擬人類隨機延遲"""
    if a is None or b is None:
        a, b = (0.35, 0.9)
    time.sleep(random.uniform(a, b))
