import discord

TOKEN = 'MTE1NTAyNDYzMjc5ODI1NzI0Mg.Gy4Hmo.SkRvJlE2mka0eMQEYiz18PnhWyhijeVlE0vBwE'
CHANNEL_ID = '1022914636019925015'


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
