from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import asyncio


class GetMembersPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("get_members")
    async def get_members(self, event: AstrMessageEvent):
        """管理员获取当前群所有成员的 QQ 昵称（非群名片）与 QQ 号"""
        
        # 检查是否在群聊中
        if event.get_group_id() is None:
            yield event.plain_result("❌ 该指令仅可在群聊中使用。")
            return

        group_id = event.get_group_id()
        sender_id = event.get_sender_id()

        # ---- 权限校验：仅群主/管理员可执行 ----
        try:
            # 获取发送者在群内的角色信息
            member_info = await event.bot.api.call_action(
                "get_group_member_info",
                group_id=group_id,
                user_id=sender_id
            )
            role = member_info.get("role", "member")  # owner / admin / member
            if role not in ("owner", "admin"):
                yield event.plain_result("❌ 权限不足：仅群主或管理员可执行此指令。")
                return
        except Exception as e:
            logger.error(f"获取成员角色失败: {e}")
            yield event.plain_result("❌ 权限校验失败，请确保机器人有获取群成员信息的权限。")
            return

        logger.info(f"管理员 {sender_id} 在群 {group_id} 执行了 get_members")

        # 获取群成员列表
        try:
            members = await event.bot.api.call_action(
                "get_group_member_list",
                group_id=group_id
            )
        except Exception as e:
            logger.error(f"获取群成员列表失败: {e}")
            yield event.plain_result(f"❌ 获取失败：{str(e)}")
            return

        if not members:
            yield event.plain_result("⚠️ 该群暂无成员。")
            return

        # 提取所有成员的 QQ 号
        user_ids = [m.get("user_id") for m in members if m.get("user_id")]
        if not user_ids:
            yield event.plain_result("⚠️ 未获取到有效成员。")
            return

        # 并发获取每个成员的全局昵称（限制并发数，避免被限频）
        sem = asyncio.Semaphore(10)

        async def get_nickname(uin: int):
            async with sem:
                try:
                    info = await event.bot.api.call_action(
                        "get_stranger_info",
                        user_id=uin
                    )
                    nickname = info.get("nickname", str(uin))
                    return uin, nickname
                except Exception as e:
                    logger.warning(f"获取用户 {uin} 昵称失败: {e}")
                    return uin, str(uin)

        tasks = [get_nickname(uin) for uin in user_ids]
        results = await asyncio.gather(*tasks)

        # 按 QQ 号排序
        results.sort(key=lambda x: int(x[0]))

        # 构建输出（格式：昵称：QQ号）
        lines = [f"{nickname}：{uin}" for uin, nickname in results]
        total = len(lines)
        header = f"📋 群 {group_id} 成员列表（共 {total} 人）：\n\n"

        # 分段发送（防止消息过长）
        if len(header) + sum(len(line) + 1 for line in lines) > 1500:
            chunk_size = 100
            for i in range(0, total, chunk_size):
                chunk_lines = lines[i:i + chunk_size]
                chunk_header = f"📋 群成员 ({i+1}-{min(i+chunk_size, total)}/{total})：\n"
                yield event.plain_result(chunk_header + "\n".join(chunk_lines))
        else:
            yield event.plain_result(header + "\n".join(lines))

    async def terminate(self):
        pass
