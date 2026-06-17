import discord

import os

# SECURITY: the original hardcoded token has been redacted. It was committed to
# git history and must be considered compromised — rotate/revoke it in the
# Discord developer portal. Read secrets from the environment instead.
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')


class Discord(discord.Client):
    def __init__(self):
        self.CID = CHANNEL_ID
        self.channel = self.get_channel(int(self.CID))

    async def on_ready(self):
        await self.channel.send('Hi! Me at the Discord:) - YammyQuant Bot')

    def send_msg(self, msg):
        await self.channel.send(msg)


def get_client():
    intents = discord.Intents.default()
    intents.message_content = True
    client = Discord(intents=intents)
    client.run(TOKEN)
    return client
