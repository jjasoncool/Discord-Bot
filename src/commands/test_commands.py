import logging
import discord
import traceback
from discord import app_commands
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

class TestCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 斜線命令
    @app_commands.command(name="echo", description="讓機器人回傳一段訊息")
    @app_commands.describe(
        message="要回傳的訊息",
        private="是否只有您能看到回應 (默認: 是)"
    )
    async def echo_cmd(self, interaction: discord.Interaction, message: str, private: bool = False):
        """斜線命令：回傳使用者輸入的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /echo 斜線命令，參數: message="{message}", private={private}')
        await interaction.response.send_message(
            f'📣 {interaction.user.mention} 說: {message}',
            ephemeral=private
        )    # list_channels 命令已移至 management_commands.py

    @app_commands.command(name="anonymous", description="匿名發送訊息到當前頻道")
    @app_commands.describe(message="要匿名發送的訊息")
    async def anonymous_cmd(self, interaction: discord.Interaction, message: str):
        """斜線命令：匿名發送訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /anonymous 斜線命令，訊息: "{message}"')

        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用！", ephemeral=True)
            return

        target_channel = interaction.channel
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("目標頻道必須是文字頻道或討論串！", ephemeral=True)
            return

        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(f"我沒有權限在 {target_channel.mention} 發送訊息！", ephemeral=True)
            return

        try:
            await target_channel.send(f"匿名訊息: {message}")
            await interaction.response.send_message("您的匿名訊息已成功發送。", ephemeral=True)
            logger.info(f"匿名訊息已發送到 {target_channel.name}")
        except Exception as e:
            logger.error(f"發送匿名訊息時發生錯誤: {str(e)}")
            await interaction.response.send_message("發送訊息時發生錯誤，請稍後再試。", ephemeral=True)

    @app_commands.command(name="list_forum_posts", description="列出特定論壇頻道的前20則貼文")
    async def list_forum_posts_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出特定論壇頻道的前20則貼文"""
        logger.info(f'收到來自 {interaction.user} 的 /list_forum_posts 命令')

        # 檢查是否在伺服器中
        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用！", ephemeral=True)
            return

        # 獲取可見的論壇頻道
        forum_channels = [
            ch for ch in interaction.guild.channels
            if isinstance(ch, discord.ForumChannel) and ch.permissions_for(interaction.user).view_channel
        ]
        if not forum_channels:
            await interaction.response.send_message("您沒有權限查看此伺服器中的任何論壇頻道。", ephemeral=True)
            return

        # 創建選擇頻道的嵌入訊息
        embed = discord.Embed(
            title="選擇一個論壇頻道",
            description="請從以下論壇頻道中選擇一個以查看前20則貼文：",
            color=discord.Color.blue()
        )
        for i, channel in enumerate(forum_channels, 1):
            embed.add_field(name=f"{i}. {channel.name}", value=f"ID: {channel.id}", inline=False)

        # 創建下拉選單
        select = discord.ui.Select(
            placeholder="選擇一個論壇頻道...",
            options=[
                discord.SelectOption(label=channel.name, value=str(channel.id), description=f"ID: {channel.id}")
                for channel in forum_channels
            ]
        )

        async def select_callback(interaction: discord.Interaction):
            """處理下拉選單的回調，顯示選定頻道的前20則貼文"""
            logger.info(f'開始執行 select_callback，選擇的頻道ID: {select.values[0]}')
            try:
                channel_id = int(select.values[0])
                channel = interaction.guild.get_channel(channel_id)
                if not isinstance(channel, discord.ForumChannel):
                    await interaction.response.send_message("無效的論壇頻道，請重試。", ephemeral=True)
                    return

                # 檢查機器人權限
                if not channel.permissions_for(interaction.guild.me).read_message_history:
                    logger.error(f"機器人缺少讀取訊息歷史權限，頻道: {channel.name}")
                    await interaction.response.send_message("機器人缺少讀取訊息歷史的權限！", ephemeral=True)
                    return

                # 獲取活躍和歸檔貼文
                threads = channel.threads[:]
                logger.info(f"獲取活躍貼文數量: {len(threads)}，頻道: {channel.name}")
                try:
                    archived_threads = []
                    async for thread in channel.archived_threads(limit=20):  # 符合 API 限制
                        archived_threads.append(thread)
                    logger.info(f"獲取歸檔貼文數量: {len(archived_threads)}，頻道: {channel.name}")
                    threads.extend(archived_threads)
                except discord.HTTPException as e:
                    if e.status == 429:  # 速率限制
                        retry_after = e.retry_after
                        logger.warning(f"觸發速率限制，將在 {retry_after} 秒後重試")
                        await asyncio.sleep(retry_after)
                        async for thread in channel.archived_threads(limit=20):
                            archived_threads.append(thread)
                        threads.extend(archived_threads)
                    else:
                        logger.error(f"獲取歸檔貼文失敗: {str(e)}")
                        await interaction.response.send_message("無法獲取歸檔貼文，請稍後再試。", ephemeral=True)
                        return

                if not threads:
                    await interaction.response.send_message("此論壇頻道中沒有任何貼文。", ephemeral=True)
                    return

                # 記錄所有貼文詳細資訊
                for thread in threads:
                    logger.info(f"貼文: {thread.name}, ID: {thread.id}, 創建時間: {thread.created_at}, 歸檔: {thread.archived}, 鎖定: {thread.locked}")

                # 按創建時間排序，從新到舊
                threads.sort(key=lambda t: t.created_at, reverse=True)

                # 創建貼文列表嵌入訊息
                embed = discord.Embed(
                    title=f"{channel.name} 論壇頻道的前20則貼文",
                    description="以下是此論壇頻道中的前20則貼文：",
                    color=discord.Color.green()
                )
                for i, thread in enumerate(threads[:20], 1):
                    owner_mention = "未知使用者"
                    if thread.owner_id:
                        try:
                            owner = await interaction.guild.fetch_member(thread.owner_id)
                            owner_mention = owner.mention if owner else "未知使用者 (已離開群組)"
                        except discord.NotFound:
                            owner_mention = "未知使用者 (已離開群組)"
                        except Exception as e:
                            logger.error(f"獲取貼文擁有者失敗: {str(e)}")
                    tags = ", ".join(tag.name for tag in thread.applied_tags) if thread.applied_tags else "無標籤"
                    embed.add_field(
                        name=f"貼文 {i}: {thread.name}",
                        value=f"由 {owner_mention} 創建於 {thread.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n標籤: {tags}",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f'成功列出貼文，頻道: {channel.name}')
            except Exception as e:
                error_details = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(f'select_callback 錯誤: {str(e)}\n詳細錯誤信息:\n{error_details}')
                await interaction.response.send_message("發生錯誤，請稍後再試。", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # 傳統前綴命令
    @commands.command(name='ping')
    async def ping(self, ctx):
        """回應一個 Pong 訊息，用於測試機器人是否在線"""
        logger.info(f'收到來自 {ctx.author} 的 ping 前綴命令')
        await ctx.send('Pong!')

    @commands.command(name='helloworld')
    async def hello_world(self, ctx):
        """回應一個 Hello World 訊息"""
        logger.info(f'收到來自 {ctx.author} 的 helloworld 前綴命令')
        await ctx.send(f'👋 Hello World! 您好，{ctx.author.mention}！我是一個由 Discord.py 驅動的機器人。')


    @app_commands.command(name="multi_select_demo", description="示範多選功能的命令")
    async def multi_select_demo_cmd(self, interaction: discord.Interaction):
        """斜線命令：示範多選功能"""
        logger.info(f'收到來自 {interaction.user} 的 /multi_select_demo 命令')

        # 定義選項
        OPTIONS = [
            {"label": "選項 1", "value": "option1", "description": "第一個選項"},
            {"label": "選項 2", "value": "option2", "description": "第二個選項"},
            {"label": "選項 3", "value": "option3", "description": "第三個選項"},
            {"label": "選項 4", "value": "option4", "description": "第四個選項"},
            {"label": "選項 5", "value": "option5", "description": "第五個選項"},
            {"label": "選項 6", "value": "option6", "description": "第六個選項"},
            {"label": "選項 7", "value": "option7", "description": "第七個選項"},
            {"label": "選項 8", "value": "option8", "description": "第八個選項"},
            {"label": "選項 9", "value": "option9", "description": "第九個選項"},
            {"label": "選項 10", "value": "option10", "description": "第十個選項"},
            {"label": "選項 11", "value": "option11", "description": "第十一個選項"},
            {"label": "選項 12", "value": "option12", "description": "第十二個選項"},
            {"label": "選項 13", "value": "option13", "description": "第十三個選項"},
            {"label": "選項 14", "value": "option14", "description": "第十四個選項"},
            {"label": "選項 15", "value": "option15", "description": "第十五個選項"}
        ]

        # 創建多選下拉選單
        select = discord.ui.Select(
            placeholder="選擇多個選項...",
            min_values=1,
            max_values=len(OPTIONS),
            options=[discord.SelectOption(**opt) for opt in OPTIONS]
        )

        async def select_callback(interaction: discord.Interaction):
            """處理多選下拉選單的回調，進入數量指定階段"""
            logger.info(f'開始執行 multi_select_demo select_callback，選擇的選項: {select.values}')
            try:
                if not select.values:
                    await interaction.response.send_message("您未選擇任何選項。", ephemeral=True)
                    return

                selected_items = {value: 1 for value in select.values}
                items_per_page = 5
                total_pages = (len(selected_items) + items_per_page - 1) // items_per_page
                current_page = 0

                def create_embed(page):
                    embed = discord.Embed(
                        title=f"選取項目 - 第 {page + 1} 頁 / {total_pages} 頁",
                        description="請使用「編輯」按鈕來設定數量，或使用按鈕切換頁面。",
                        color=discord.Color.blue()
                    )
                    start_idx = page * items_per_page
                    end_idx = min(start_idx + items_per_page, len(selected_items))
                    page_items = list(selected_items.keys())[start_idx:end_idx]
                    for value in page_items:
                        label = next(opt['label'] for opt in OPTIONS if opt['value'] == value)
                        embed.add_field(
                            name=label,
                            value=f"數量: {selected_items[value]}",
                            inline=False
                        )
                    return embed

                def create_view(page):
                    view = discord.ui.View()
                    if total_pages > 1:
                        if page > 0:
                            prev_button = discord.ui.Button(label="上一頁", style=discord.ButtonStyle.blurple)
                            prev_button.callback = lambda inter: update_page(inter, page - 1)
                            view.add_item(prev_button)
                        if page < total_pages - 1:
                            next_button = discord.ui.Button(label="下一頁", style=discord.ButtonStyle.blurple)
                            next_button.callback = lambda inter: update_page(inter, page + 1)
                            view.add_item(next_button)
                    edit_button = discord.ui.Button(label="編輯", style=discord.ButtonStyle.green)
                    edit_button.callback = lambda inter: edit_items(inter, page)
                    view.add_item(edit_button)
                    finish_button = discord.ui.Button(label="完成", style=discord.ButtonStyle.red)
                    finish_button.callback = lambda inter: finish_editing(inter)
                    view.add_item(finish_button)
                    return view

                async def update_page(interaction: discord.Interaction, new_page):
                    nonlocal current_page
                    current_page = new_page
                    await interaction.response.edit_message(embed=create_embed(current_page), view=create_view(current_page))

                async def edit_items(interaction: discord.Interaction, page):
                    start_idx = page * items_per_page
                    end_idx = min(start_idx + items_per_page, len(selected_items))
                    page_items = list(selected_items.keys())[start_idx:end_idx]

                    modal = discord.ui.Modal(title=f"編輯數量 - 第 {page + 1} 頁")
                    inputs = []
                    for value in page_items:
                        label = next(opt['label'] for opt in OPTIONS if opt['value'] == value)
                        qty_input = discord.ui.TextInput(
                            label=label,
                            placeholder="輸入數量（整數）",
                            default=str(selected_items[value])
                        )
                        modal.add_item(qty_input)
                        inputs.append((value, qty_input))

                    async def on_submit(interaction: discord.Interaction):
                        try:
                            for value, input_field in inputs:
                                qty = int(input_field.value)
                                if qty < 1:
                                    await interaction.response.send_message(f"{input_field.label} 的數量不能小於 1，請重試。", ephemeral=True)
                                    return
                                selected_items[value] = qty
                            await interaction.response.send_message(f"已更新第 {page + 1} 頁的數量。", ephemeral=True)
                            await interaction.followup.edit_message(interaction.message.id, embed=create_embed(current_page), view=create_view(current_page))
                        except ValueError:
                            await interaction.response.send_message("所有數量必須是有效的整數，請重試。", ephemeral=True)

                    modal.on_submit = on_submit
                    await interaction.response.send_modal(modal)

                async def finish_editing(interaction: discord.Interaction):
                    summary_embed = discord.Embed(
                        title="最終確認",
                        description="您的選擇如下：",
                        color=discord.Color.green()
                    )
                    for value in selected_items:
                        label = next(opt['label'] for opt in OPTIONS if opt['value'] == value)
                        summary_embed.add_field(name=label, value=f"數量: {selected_items[value]}", inline=False)
                    await interaction.response.edit_message(embed=summary_embed, view=None)
                    logger.info(f'用戶已完成選擇: {selected_items}')

                await interaction.response.send_message(embed=create_embed(current_page), view=create_view(current_page), ephemeral=True)
            except Exception as e:
                error_details = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(f'multi_select_demo select_callback 錯誤: {str(e)}\n詳細錯誤信息:\n{error_details}')
                await interaction.response.send_message("發生錯誤，請稍後再試。", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message("請從以下選項中選擇一個或多個：", view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TestCommands(bot))
    # 不需要在這裡同步命令，我們將在主程式中一次性同步所有命令
