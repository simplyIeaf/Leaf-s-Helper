import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, TextInputStyle, SlashOption, Embed
import json
import os
import datetime
import pytz
import uuid
import requests
import base64
import re
from better_profanity import profanity
from keep_alive import keep_alive

PARIS_TZ = pytz.timezone('Europe/Paris')
OWNER_NAME = "simplyieaf"
REPO = "simplyIeaf/Leaf-s-Helper"
FILE_PATH = "scheduled_posts.json"
PROJECT_URL = "okay-jourdan-leaf54355666654-f8412d06.koyeb.app/"

profanity.load_censor_words()

def load_data():
    try:
        url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
        headers = {"Authorization": f"token {os.environ['GH_TOKEN']}"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = base64.b64decode(r.json()['content']).decode('utf-8')
            return json.loads(content)
    except: pass
    return {"posts": [], "messages": [], "autoroles": [], "automod": {}, "welcome_channel": None}

def save_data(data):
    try:
        url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
        headers = {"Authorization": f"token {os.environ['GH_TOKEN']}"}
        r = requests.get(url, headers=headers)
        sha = r.json()['sha'] if r.status_code == 200 else None
        content = json.dumps(data, indent=4)
        payload = {"message": "Sync", "content": base64.b64encode(content.encode()).decode()}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except: pass

class ScheduleModal(nextcord.ui.Modal):
    def __init__(self, type, channel):
        super().__init__(title=f"Schedule {type}")
        self.type, self.channel = type, channel
        self.date_in = nextcord.ui.TextInput(label="Date (DD/MM/YY)", min_length=8, max_length=8)
        self.time_in = nextcord.ui.TextInput(label="Time (HH:MM AM/PM)", min_length=8, max_length=8)
        self.title_in = nextcord.ui.TextInput(label="Title", max_length=100)
        self.content_in = nextcord.ui.TextInput(label="Content", style=TextInputStyle.paragraph, max_length=1500)
        self.pings_in = nextcord.ui.TextInput(label="Mentions (IDs)", required=False)
        for i in [self.date_in, self.time_in, self.title_in, self.content_in, self.pings_in]: self.add_item(i)

    async def callback(self, interaction: Interaction):
        try:
            ts = PARIS_TZ.localize(datetime.datetime.strptime(f"{self.date_in.value} {self.time_in.value.upper()}", "%d/%m/%y %I:%M %p")).timestamp()
            data = load_data()
            entry = {"id": str(uuid.uuid4())[:6], "channel_id": self.channel.id, "title": self.title_in.value, "content": self.content_in.value, "pings": self.pings_in.value, "timestamp": ts, "readable": f"{self.date_in.value} {self.time_in.value}"}
            data["posts" if self.type == "post" else "messages"].append(entry)
            save_data(data)
            await interaction.response.send_message("Scheduled.", ephemeral=True)
        except: await interaction.response.send_message("Format Error.", ephemeral=True)

class SimpleBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        self.main_loop.start()
        print(f"Logged in as {self.user}")

    async def on_member_join(self, member):
        data = load_data()
        for role_id in data.get("autoroles", []):
            role = member.guild.get_role(int(role_id))
            if role: await member.add_roles(role)

        if data.get("welcome_channel"):
            channel = self.get_channel(int(data["welcome_channel"]))
            if channel:
                embed = Embed(title=f"Welcome to {member.guild.name}!", description=f"Hello {member.mention}, we are glad to have you here!", color=0x5865F2)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="Member Count", value=f"#{member.guild.member_count}")
                embed.set_footer(text=f"ID: {member.id}")
                await channel.send(embed=embed)

    async def on_message(self, message):
        if message.author.bot or message.author.name == OWNER_NAME: return
        data = load_data()
        settings = data.get("automod", {}).get(str(message.channel.id))

        if settings:
            if settings.get("ai_mod") and profanity.contains_profanity(message.content):
                await message.delete()
                return await message.channel.send(f"{message.author.mention} Watch your language!", delete_after=3)
            if settings.get("no_links") and re.search(r"http[s]?://", message.content):
                await message.delete()
                return await message.channel.send(f"{message.author.mention} No links!", delete_after=3)

    @tasks.loop(minutes=5)
    async def main_loop(self):
        try: requests.get(PROJECT_URL)
        except: pass
        data, now, changed = load_data(), datetime.datetime.now().timestamp(), False
        for p in data["posts"][:]:
            if now >= p["timestamp"]:
                c = self.get_channel(p["channel_id"])
                if isinstance(c, nextcord.ForumChannel):
                    await c.create_thread(name=p["title"], content=f"{p['content']}\n\n{p['pings']}")
                elif c is None:
                    # Fallback to fetch if not in cache
                    try:
                        c = await self.fetch_channel(p["channel_id"])
                        if isinstance(c, nextcord.ForumChannel):
                            await c.create_thread(name=p["title"], content=f"{p['content']}\n\n{p['pings']}")
                    except: pass
                data["posts"].remove(p); changed = True
        for m in data["messages"][:]:
            if now >= m["timestamp"]:
                c = self.get_channel(m["channel_id"])
                if isinstance(c, nextcord.TextChannel):
                    await c.send(f"**{m['title']}**\n{m['content']}\n{m['pings']}")
                elif c is None:
                    try:
                        c = await self.fetch_channel(m["channel_id"])
                        if isinstance(c, nextcord.TextChannel):
                            await c.send(f"**{m['title']}**\n{m['content']}\n{m['pings']}")
                    except: pass
                data["messages"].remove(m); changed = True
        if changed: save_data(data)

bot = SimpleBot(intents=nextcord.Intents.all())

async def check_user(interaction: Interaction):
    if interaction.user is None or interaction.user.name != OWNER_NAME:
        await interaction.response.send_message("Denied.", ephemeral=True)
        return False
    return True

@bot.slash_command()
async def schedulepost(interaction: Interaction, forum: nextcord.ForumChannel):
    if await check_user(interaction): await interaction.response.send_modal(ScheduleModal("post", forum))

@bot.slash_command()
async def schedulemsg(interaction: Interaction, channel: nextcord.TextChannel):
    if await check_user(interaction): await interaction.response.send_modal(ScheduleModal("message", channel))

@bot.slash_command()
async def setwelcome(interaction: Interaction, channel: nextcord.TextChannel):
    if await check_user(interaction):
        data = load_data()
        data["welcome_channel"] = str(channel.id)
        save_data(data); await interaction.response.send_message(f"Welcome channel set to {channel.mention}", ephemeral=True)

@bot.slash_command()
async def addautorole(interaction: Interaction, role: nextcord.Role):
    if await check_user(interaction):
        data = load_data()
        if str(role.id) not in data["autoroles"]: data["autoroles"].append(str(role.id))
        save_data(data); await interaction.response.send_message(f"Auto-role {role.name} added.", ephemeral=True)

@bot.slash_command()
async def purgeuser(interaction: Interaction, user: nextcord.Member, timeframe: str = SlashOption(choices={"Day": "1", "Week": "7", "Month": "30", "Year": "365"}, required=False)):
    if await check_user(interaction):
        await interaction.response.defer(ephemeral=True)
        limit = datetime.datetime.now() - datetime.timedelta(days=int(timeframe or 365))
        deleted = 0
        if interaction.guild is None:
            return await interaction.followup.send("This command must be used in a server.")
        for channel in interaction.guild.text_channels:
            try:
                def check(m): return m.author == user and m.created_at.replace(tzinfo=None) > limit
                purged = await channel.purge(limit=10000, check=check)
                deleted += len(purged)
            except: continue
        await interaction.followup.send(f"Purged {deleted} messages.")

@bot.slash_command()
async def automod(interaction: Interaction, channel: nextcord.TextChannel, aimod: bool, links: bool, enable: bool):
    if await check_user(interaction):
        data = load_data()
        if enable: data["automod"][str(channel.id)] = {"ai_mod": aimod, "no_links": links}
        elif str(channel.id) in data["automod"]: del data["automod"][str(channel.id)]
        save_data(data); await interaction.response.send_message("AutoMod Configured.", ephemeral=True)

keep_alive()
bot.run(os.environ['TOKEN'])
