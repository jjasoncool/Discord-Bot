"""音樂播放器指令入口點
讓 COMMAND_MODULES 可以統一使用 'commands.music_commands' 格式
"""
from discord.ext import commands
from music.cog import setup as music_setup

async def setup(bot: commands.Bot):
    """discord.py 自動呼叫的 setup 函數"""
    await music_setup(bot)
