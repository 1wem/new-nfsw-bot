import os
import asyncio
from discord.ext import commands, tasks
from discord import Intents, app_commands, Interaction, TextChannel, Embed
from pymongo import MongoClient
import asyncpraw
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
import random
import logging

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT')

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('discord_bot')

# MongoDB setup
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client['reddit_discord_bot']
mappings_col = db['subreddit_channel_mappings']
posted_col = db['posted_media']
settings_col = db['settings']

# Reddit setup
reddit = asyncpraw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

# Discord bot setup
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Flask keep-alive server
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"
def run_flask():
    app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# Helper: Get or set fetch interval (in minutes)
def get_fetch_interval():
    doc = settings_col.find_one({"_id": "interval"})
    return doc["minutes"] if doc else 10  # default 10 min
def set_fetch_interval(minutes: int):
    settings_col.update_one({"_id": "interval"}, {"$set": {"minutes": minutes}}, upsert=True)

# Helper: Get or set posts per interval
POSTS_PER_KEY = "posts_per_interval"
def get_posts_per_interval():
    doc = settings_col.find_one({"_id": POSTS_PER_KEY})
    return doc["count"] if doc else 1  # default 1 post per interval

def set_posts_per_interval(count: int):
    settings_col.update_one({"_id": POSTS_PER_KEY}, {"$set": {"count": count}}, upsert=True)

# Helper: Check if user is admin
async def is_admin(interaction: Interaction):
    member = interaction.user if hasattr(interaction, 'user') else None
    if not member or not hasattr(member, 'guild_permissions'):
        return False
    return member.guild_permissions.administrator

# Decorator for admin-only commands
async def admin_only(interaction: Interaction):
    if not await is_admin(interaction):
        await interaction.response.send_message("❌ You must be a server admin to use this command.", ephemeral=True)
        return False
    return True

# Slash command: Set subreddit to channel mapping
@tree.command(name="setsubreddit", description="Map a subreddit to a channel.")
@app_commands.describe(subreddit="Subreddit name (without r/)", channel="Channel to post in")
async def setsubreddit(interaction: Interaction, subreddit: str, channel: TextChannel):
    if not await admin_only(interaction):
        return
    subreddit = subreddit.lower()
    try:
        sub = await reddit.subreddit(subreddit)
        await sub.load()
        if not sub.over18:
            await interaction.response.send_message(f"❌ r/{subreddit} is not marked as NSFW.", ephemeral=True)
            return
    except Exception as e:
        logger.error(f"Error checking subreddit NSFW: {e}")
        await interaction.response.send_message(f"❌ Could not find r/{subreddit}.", ephemeral=True)
        return
    mappings_col.update_one({"subreddit": subreddit}, {"$set": {"channel_id": str(channel.id)}}, upsert=True)
    logger.info(f"Mapped r/{subreddit} to channel {channel.id}")
    await interaction.response.send_message(f"✅ Mapped r/{subreddit} to {channel.mention}.", ephemeral=True)

# Slash command: Remove subreddit mapping
@tree.command(name="removesubreddit", description="Remove a subreddit to channel mapping.")
@app_commands.describe(subreddit="Subreddit name (without r/)")
async def removesubreddit(interaction: Interaction, subreddit: str):
    if not await admin_only(interaction):
        return
    subreddit = subreddit.lower()
    result = mappings_col.delete_one({"subreddit": subreddit})
    if result.deleted_count:
        logger.info(f"Removed mapping for r/{subreddit}")
        await interaction.response.send_message(f"✅ Removed mapping for r/{subreddit}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ No mapping found for r/{subreddit}.", ephemeral=True)

# Slash command: List all mappings
@tree.command(name="listmappings", description="List all subreddit to channel mappings.")
async def listmappings(interaction: Interaction):
    mappings = list(mappings_col.find())
    if not mappings:
        await interaction.response.send_message("No mappings set.", ephemeral=True)
        return
    msg = "**Subreddit → Channel**\n"
    for m in mappings:
        channel = interaction.guild.get_channel(int(m["channel_id"]))
        channel_mention = channel.mention if channel else f"(ID: {m['channel_id']})"
        msg += f"r/{m['subreddit']} → {channel_mention}\n"
    await interaction.response.send_message(msg, ephemeral=True)

# Slash command: Set fetch interval
@tree.command(name="setinterval", description="Set the fetch interval in minutes.")
@app_commands.describe(minutes="Interval in minutes (min 1)")
async def setinterval(interaction: Interaction, minutes: int):
    if not await admin_only(interaction):
        return
    if minutes < 1:
        await interaction.response.send_message("❌ Interval must be at least 1 minute.", ephemeral=True)
        return
    set_fetch_interval(minutes)
    logger.info(f"Fetch interval set to {minutes} minutes")
    await interaction.response.send_message(f"✅ Fetch interval set to {minutes} minutes.", ephemeral=True)

# Slash command: Set posts per interval
@tree.command(name="setposts", description="Set how many posts per channel per interval.")
@app_commands.describe(count="Number of posts per channel per interval (min 1, max 10)")
async def setposts(interaction: Interaction, count: int):
    if not await admin_only(interaction):
        return
    if count < 1 or count > 10:
        await interaction.response.send_message("❌ Count must be between 1 and 10.", ephemeral=True)
        return
    set_posts_per_interval(count)
    logger.info(f"Posts per interval set to {count}")
    await interaction.response.send_message(f"✅ Will send {count} post(s) per channel per interval.", ephemeral=True)

# Slash command: Show posts per interval
@tree.command(name="showposts", description="Show how many posts per channel per interval.")
async def showposts(interaction: Interaction):
    count = get_posts_per_interval()
    await interaction.response.send_message(f"Currently set to send {count} post(s) per channel per interval.", ephemeral=True)

# Helper: Check if media was already posted
def was_posted(post_id):
    return posted_col.find_one({"post_id": post_id}) is not None

def mark_posted(post_id):
    posted_col.insert_one({"post_id": post_id})

# Helper: Extract media URL from Reddit submission
# Returns (media_url, is_image, is_gif, is_redgif, is_video)
async def extract_media(sub):
    if hasattr(sub, "post_hint"):
        if sub.post_hint == "image":
            return (sub.url, True, sub.url.endswith(".gif"), False, False)
        if sub.post_hint == "hosted:video" and hasattr(sub, "media") and sub.media:
            # Allow Reddit-hosted videos
            reddit_video = sub.media.get("reddit_video")
            if reddit_video:
                return (reddit_video.get("fallback_url"), False, False, False, True)
        if sub.post_hint == "rich:video" and "redgifs" in sub.url:
            # Redgifs: try to get direct .mp4
            return (sub.url, False, False, True, False)
    # Fallback: check url extension
    if sub.url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
        return (sub.url, True, sub.url.endswith('.gif'), False, False)
    if sub.url.endswith(('.mp4', '.webm', '.mov')):
        # Allow direct video links
        return (sub.url, False, False, False, True)
    return (sub.url, False, False, False, False)

# Background task: Fetch and post media
@tasks.loop(minutes=1)
async def fetch_and_post():
    interval = get_fetch_interval()
    posts_per = get_posts_per_interval()
    if fetch_and_post.current_loop % interval != 0:
        return
    mappings = list(mappings_col.find())
    for mapping in mappings:
        subreddit = mapping["subreddit"]
        channel_id = int(mapping["channel_id"])
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        try:
            sub = await reddit.subreddit(subreddit, fetch=True)
            submissions = [s async for s in sub.new(limit=30) if s.over_18]
            random.shuffle(submissions)
            sent = 0
            for submission in submissions:
                if sent >= posts_per:
                    break
                if was_posted(submission.id):
                    continue
                media_url, is_image, is_gif, is_redgif, is_video = await extract_media(submission)
                if not (is_image or is_gif or is_redgif or is_video):
                    continue
                embed = Embed(title=submission.title[:256], url=f"https://reddit.com{submission.permalink}", description=f"Posted by u/{submission.author}")
                embed.set_footer(text=f"r/{subreddit}")
                if is_image or is_gif:
                    embed.set_image(url=media_url)
                elif is_redgif:
                    embed.add_field(name="Redgifs Video", value=media_url, inline=False)
                elif is_video:
                    embed.add_field(name="Video", value=media_url, inline=False)
                else:
                    embed.add_field(name="Media", value=media_url, inline=False)
                try:
                    await channel.send(embed=embed)
                    mark_posted(submission.id)
                    sent += 1
                    logger.info(f"Posted media from r/{subreddit} to channel {channel.id}")
                except Exception as e:
                    logger.error(f"Failed to send to {channel}: {e}")
        except Exception as e:
            logger.error(f"Error fetching from r/{subreddit}: {e}")

# Slash command: Force send latest media from subreddit to channel
@tree.command(name="forcesend", description="Force send the latest media from a subreddit to a channel.")
@app_commands.describe(subreddit="Subreddit name (without r/)", channel="Channel to post in")
async def forcesend(interaction: Interaction, subreddit: str, channel: TextChannel):
    if not await admin_only(interaction):
        return
    subreddit = subreddit.lower()
    try:
        sub = await reddit.subreddit(subreddit, fetch=True)
        submissions = [s async for s in sub.new(limit=10) if s.over_18]
        for submission in submissions:
            media_url, is_image, is_gif, is_redgif, is_video = await extract_media(submission)
            if not (is_image or is_gif or is_redgif or is_video):
                continue
            embed = Embed(title=submission.title[:256], url=f"https://reddit.com{submission.permalink}", description=f"Posted by u/{submission.author}")
            embed.set_footer(text=f"r/{subreddit}")
            if is_image or is_gif:
                embed.set_image(url=media_url)
            elif is_redgif:
                embed.add_field(name="Redgifs Video", value=media_url, inline=False)
            elif is_video:
                embed.add_field(name="Video", value=media_url, inline=False)
            else:
                embed.add_field(name="Media", value=media_url, inline=False)
            await channel.send(embed=embed)
            logger.info(f"Force sent media from r/{subreddit} to channel {channel.id}")
            await interaction.response.send_message(f"✅ Forced sent media from r/{subreddit} to {channel.mention}.", ephemeral=True)
            return
        await interaction.response.send_message(f"❌ No suitable media found in r/{subreddit}.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error in /forcesend: {e}")
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# Sync commands on startup
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    keep_alive()
    try:
        bot.loop.create_task(tree.sync())
        print("Slash commands synced.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    if not fetch_and_post.is_running():
        fetch_and_post.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN) 
