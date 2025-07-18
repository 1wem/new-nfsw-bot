# NSFW Reddit Media Discord Bot

## Features
- Fetches NSFW media (Redgifs, Reddit videos, images, etc.) from multiple subreddits
- Posts each subreddit's media to a specific Discord channel (configurable via slash commands)
- Avoids reposting the same media
- Stores mappings and history in MongoDB
- Change fetch interval with a slash command
- Deployable on Render with a keep-alive web server

## Setup Instructions

### 1. Clone the Repository
```
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Install Dependencies
```
pip install -r requirements.txt
```

### 3. Create a `.env` File
Create a `.env` file in the root directory with the following content:
```
DISCORD_TOKEN=your_discord_bot_token
MONGODB_URI=your_mongodb_connection_string
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_user_agent
```

### 4. Set Up Discord Bot
- Create a bot at https://discord.com/developers/applications
- Enable the "MESSAGE CONTENT INTENT" and "SERVER MEMBERS INTENT"
- Invite the bot to your server with the appropriate permissions (Send Messages, Manage Channels, etc.)

### 5. Set Up Reddit App
- Go to https://www.reddit.com/prefs/apps
- Create a new script app and get the client ID, secret, and set a user agent

### 6. Set Up MongoDB
- Use MongoDB Atlas or your own MongoDB instance
- Get the connection string and add it to your `.env`

### 7. Deploy on Render
- Create a new web service on Render
- Use `python main.py` as the start command
- Add your environment variables in the Render dashboard

### 8. Run the Bot Locally
```
python main.py
```

## Usage
- Use `/setsubreddit subreddit:<name> channel:<#channel>` to map a subreddit to a channel
- Use `/removesubreddit subreddit:<name>` to remove a mapping
- Use `/setinterval minutes:<number>` to change the fetch interval
- Use `/listmappings` to list all mappings

---

**Note:** This bot is for NSFW subreddits only. Make sure your Discord channels are marked as NSFW. 