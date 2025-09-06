import discord
from discord.ext import commands
import aiohttp
import os
import re

# --- Configuration ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Enable all necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.messages = True


class StatefulRelayBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

        self.message_map = {}

        self.relay_map = {
            # Channel A ID : Channel B Webhook URL
            1402684679521308742: "https://discord.com/api/webhooks/1402685151963644004/k0LFa1MrZ2VT5c1E-ze4B4fpONRvVJxyWY0BLDSLzP1IE0zTYGW1uEWm_uMJC92QeBSe",
            # Channel B ID : Channel A Webhook URL
            1402685090408042580: "https://discord.com/api/webhooks/1402684721401561250/aXq7TOn4YVaO1Z0kKMuFd_GFy7RADGCRZmRTnbv8Tft_TM51DRyYKyL_NI1NhluyB1pw"
        }
        self.session = None
        self.relay_webhook_ids = set()

    def extract_webhook_id(self, url):
        match = re.search(r'webhooks/(\d+)/', str(url))
        return int(match.group(1)) if match else None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        for url in self.relay_map.values():
            if webhook_id := self.extract_webhook_id(url):
                self.relay_webhook_ids.add(webhook_id)
        print("aiohttp session started.")
        print(f"Tracking {len(self.relay_webhook_ids)} relay webhooks to prevent loops.")

    async def on_ready(self):
        print(f"✅ Stateful Relay Bot is online as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.webhook_id and message.webhook_id in self.relay_webhook_ids:
            return
        if message.author.id == self.user.id:
            return

        if message.channel.id in self.relay_map:
            webhook_url = self.relay_map[message.channel.id]
            try:
                content_to_send = message.content
                reply_prefix = ""


                if message.reference and message.reference.message_id:
                    try:

                        replied_to_message = await message.channel.fetch_message(message.reference.message_id)
                        person_to_ping = replied_to_message.author
                        content_to_quote = replied_to_message.content

                        # Check if the message being replied to is one we relayed.
                        if replied_to_message.id in self.message_map:
                            true_original_id = self.message_map[replied_to_message.id]


                            other_channel_id = None
                            for cid in self.relay_map.keys():
                                if cid != message.channel.id:
                                    other_channel_id = cid
                                    break

                            if other_channel_id:
                                other_channel = self.get_channel(other_channel_id)

                                true_original_message = await other_channel.fetch_message(true_original_id)
                                person_to_ping = true_original_message.author
                                content_to_quote = true_original_message.content


                        if '\n' in content_to_quote and content_to_quote.startswith('Replying to'):
                            content_to_quote = content_to_quote.split('\n', 1)[1]

                        if len(content_to_quote) > 75:
                            content_to_quote = content_to_quote[:75].strip() + "..."

                        reply_prefix = (
                            f"Replying to {person_to_ping.mention}\n"
                            f"> {content_to_quote}\n"
                        )
                    except discord.NotFound:
                        pass

                final_content = reply_prefix + content_to_send

                if message.stickers:
                    sticker_urls = " ".join([sticker.url for sticker in message.stickers])
                    final_content = f"{final_content}\n{sticker_urls}".strip()

                if message.role_mentions:
                    for role in message.role_mentions:
                        final_content = final_content.replace(role.mention, f"@{role.name}")

                webhook = discord.Webhook.from_url(webhook_url, session=self.session)
                files = [await attachment.to_file() for attachment in message.attachments]
                allowed_mentions = discord.AllowedMentions(users=True, roles=False, everyone=False)
                author_avatar_url = message.author.display_avatar.url if message.author.display_avatar else None

                relayed_message = await webhook.send(
                    content=final_content,
                    username=message.author.display_name,
                    avatar_url=author_avatar_url,
                    files=files,
                    embeds=message.embeds,
                    allowed_mentions=allowed_mentions,
                    wait=True
                )

                self.message_map[message.id] = relayed_message.id
                self.message_map[relayed_message.id] = message.id

            except Exception as e:
                print(f"❌ Error relaying message: {e}")

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.message_id not in self.message_map: return
        relayed_message_id = self.message_map[payload.message_id]
        original_channel_id = payload.channel_id
        if original_channel_id not in self.relay_map: return
        webhook_url = self.relay_map[original_channel_id]

        try:
            webhook = discord.Webhook.from_url(webhook_url, session=self.session)
            channel = self.get_channel(original_channel_id)
            if not channel: return
            original_message = await channel.fetch_message(payload.message_id)

            content_to_send = original_message.content
            reply_prefix = ""

            if original_message.reference and original_message.reference.message_id:
                try:
                    replied_to_message = await channel.fetch_message(original_message.reference.message_id)
                    person_to_ping = replied_to_message.author
                    content_to_quote = replied_to_message.content

                    if replied_to_message.id in self.message_map:
                        true_original_id = self.message_map[replied_to_message.id]
                        other_channel_id = None
                        for cid in self.relay_map.keys():
                            if cid != original_message.channel.id:
                                other_channel_id = cid
                                break
                        if other_channel_id:
                            other_channel = self.get_channel(other_channel_id)
                            true_original_message = await other_channel.fetch_message(true_original_id)
                            person_to_ping = true_original_message.author
                            content_to_quote = true_original_message.content

                    if '\n' in content_to_quote and content_to_quote.startswith('Replying to'):
                        content_to_quote = content_to_quote.split('\n', 1)[1]

                    if len(content_to_quote) > 75:
                        content_to_quote = content_to_quote[:75].strip() + "..."

                    reply_prefix = (
                        f"Replying to {person_to_ping.mention}\n"
                        f"> {content_to_quote}\n"
                    )
                except discord.NotFound:
                    pass

            final_content = reply_prefix + content_to_send

            if original_message.role_mentions:
                for role in original_message.role_mentions:
                    final_content = final_content.replace(role.mention, f"@{role.name}")

            await webhook.edit_message(
                relayed_message_id,
                content=final_content,
                embeds=original_message.embeds
            )
        except Exception as e:
            print(f"❌ Error syncing edit: {e}")

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id not in self.message_map: return
        relayed_message_id = self.message_map.pop(payload.message_id, None)
        if relayed_message_id:
            self.message_map.pop(relayed_message_id, None)
        else:
            return
        original_channel_id = payload.channel_id
        if original_channel_id not in self.relay_map: return
        webhook_url = self.relay_map[original_channel_id]
        try:
            webhook = discord.Webhook.from_url(webhook_url, session=self.session)
            await webhook.delete_message(relayed_message_id)
        except Exception as e:
            print(f"❌ Error syncing delete: {e}")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot: return
        if payload.message_id not in self.message_map: return
        original_channel_id = payload.channel_id
        relayed_message_id = self.message_map[payload.message_id]
        dest_channel_id = None
        for cid in self.relay_map:
            if cid != original_channel_id:
                dest_channel_id = cid
                break
        if not dest_channel_id: return
        try:
            dest_channel = self.get_channel(dest_channel_id)
            if not dest_channel: return
            target_message = await dest_channel.fetch_message(relayed_message_id)
            await target_message.add_reaction(payload.emoji)
        except Exception as e:
            print(f"❌ Error syncing reaction add: {e}")

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.message_id not in self.message_map: return
        original_channel_id = payload.channel_id
        relayed_message_id = self.message_map[payload.message_id]
        dest_channel_id = None
        for cid in self.relay_map:
            if cid != original_channel_id:
                dest_channel_id = cid
                break
        if not dest_channel_id: return
        try:
            dest_channel = self.get_channel(dest_channel_id)
            if not dest_channel: return
            target_message = await dest_channel.fetch_message(relayed_message_id)
            await target_message.remove_reaction(payload.emoji, self.user)
        except Exception as e:
            print(f"❌ Error syncing reaction remove: {e}")


# --- Run the bot ---
if BOT_TOKEN is None:
    print("❌ ERROR: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot = StatefulRelayBot()
    bot.run(BOT_TOKEN)