import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, TextInputStyle
import json
import os
import datetime
import pytz
import uuid
import requests
import base64
from keep_alive import keep_alive

# --- CONFIGURATION ---
PARIS_TZ = pytz.timezone('Europe/Paris')
OWNER_NAME = "simplyieaf"
REPO = "simplyIeaf/Leaf-s-Helper"
FILE_PATH = "scheduled_posts.json"

# --- GITHUB STORAGE LOGIC ---
def load_data():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {os.environ['GH_TOKEN']}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        content = base64.b64decode(r.json()['content']).decode('utf-8')
        return json.loads(content)
    return []

def save_data(data):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {os.environ['GH_TOKEN']}"}
    
    # Get current file info to get the 'sha' (required for updates)
    r = requests.get(url, headers=headers)
    sha = r.json()['sha'] if r.status_code == 200 else None
    
    content = json.dumps(data, indent=4)
    payload = {
        "message": "Update scheduled posts",
        "content": base64.b64encode(content.encode('utf-8')).decode('utf-8')
    }
    if sha:
        payload["sha"] = sha
        
    requests.put(url, headers=headers, json=payload)

# --- THE INPUT FORM ---
class ForumModal(nextcord.ui.Modal):
    def __init__(self, mode, channel, task_id=None, old_data=None):
        super().__init__(title="Schedule Post" if mode == "add" else "Edit Post")
        self.mode, self.channel, self.task_id = mode, channel, task_id

        self.date_in = nextcord.ui.TextInput(label="Date (DD/MM/YY)", placeholder="25/12/26", default_value=old_data['date'] if old_data else "", min_length=8, max_length=8)
        self.time_in = nextcord.ui.TextInput(label="Time (HH:MM AM/PM)", placeholder="02:30 PM", default_value=old_data['time'] if old_data else "", min_length=8, max_length=8)
        self.title_in = nextcord.ui.TextInput(label="Forum Title", default_value=old_data['title'] if old_data else "", max_length=100)
        self.desc_in = nextcord.ui.TextInput(label="Content", default_value=old_data['desc'] if old_data else "", style=TextInputStyle.paragraph, max_length=2000)
        
        for item in [self.date_in, self.time_in, self.title_in, self.desc_in]:
            self.add_item(item)

    async def callback(self, interaction: Interaction):
        try:
            time_str = f"{self.date_in.value} {self.time_in.value.upper()}"
            dt = PARIS_TZ.localize(datetime.datetime.strptime(time_str, "%d/%m/%y %I:%M %p"))
            utc_ts = dt.astimezone(pytz.utc).timestamp()
        except:
            return await interaction.response.send_message("Format Error. Use DD/MM/YY and HH:MM AM/PM", ephemeral=True)

        data = load_data()
        if self.mode == "add":
            new_id = str(uuid.uuid4())[:6]
            data.append({"id": new_id, "channel_id": self.channel.id, "title": self.title_in.value, "description": self.desc_in.value, "timestamp": utc_ts, "readable": time_str})
            await interaction.response.send_message(f"Scheduled. ID: {new_id}", ephemeral=True)
        else:
            for t in data:
                if t['id'] == self.task_id:
                    t.update({"title": self.title_in.value, "description": self.desc_in.value, "timestamp": utc_ts, "readable": time_str})
            await interaction.response.send_message(f"Updated: {self.task_id}", ephemeral=True)
        save_data(data)

# --- BOT CLASS ---
class SimpleBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        self.poster_loop.start()

    @tasks.loop(minutes=1)
    async def poster_loop(self):
        data = load_data()
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        remaining, updated = [], False

        for t in data:
            if now >= t['timestamp']:
                chan = self.get_channel(t['channel_id'])
                if chan:
                    try:
                        await chan.create_thread(name=t['title'], content=t['description'])
                        updated = True
                        continue
                    except: pass
                updated = True
            else:
                remaining.append(t)
        
        if updated:
            save_data(remaining)

intents = nextcord.Intents.default()
bot = SimpleBot(intents=intents)

async def check_user(interaction: Interaction):
    if interaction.user.name != OWNER_NAME:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return False
    return True

@bot.slash_command(description="Schedule a forum post")
async def schedule(interaction: Interaction, forum: nextcord.ForumChannel):
    if await check_user(interaction):
        await interaction.response.send_modal(ForumModal("add", forum))

@bot.slash_command(description="List all posts")
async def listposts(interaction: Interaction):
    if await check_user(interaction):
        data = load_data()
        if not data: return await interaction.response.send_message("No posts.", ephemeral=True)
        msg = "Scheduled Posts:\n" + "\n".join([f"ID: {t['id']} | {t['title']} | {t['readable']}" for t in data])
        await interaction.response.send_message(msg, ephemeral=True)

@bot.slash_command(description="Delete a post")
async def removepost(interaction: Interaction, post_id: str):
    if await check_user(interaction):
        data = [t for t in load_data() if t['id'] != post_id]
        save_data(data)
        await interaction.response.send_message(f"Removed {post_id}", ephemeral=True)

keep_alive()
bot.run(os.environ['TOKEN'])
