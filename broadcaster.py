import embedmaker
import asyncio
from discord.channel import TextChannel
from db_io import *


async def broadcast(author, channel: TextChannel, client, admin_list, conn):
    numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    servers, embed = embedmaker.get_servers()
    msg = await channel.send(embed=embed)
    await msg.add_reaction(emoji="❌")
    x = 0
    while x < len(servers):
        await msg.add_reaction(emoji=numbers[x])
        x += 1
    future = asyncio.ensure_future(wait_for_reaction(author, msg, client, admin_list))
    while not future.done():
        res, user = await client.wait_for('reaction_add',
                                          check=lambda reaction, user: reaction.emoji == '♻️' or '❌')
        if user == author or user.id in admin_list:
            if res.message.id == msg.id:
                if res.emoji in numbers:
                    index = numbers.index(res.emoji)
                    asyncio.create_task(server_status(author, servers[index][1], servers[index][2], conn, channel, client, admin_list))


async def wait_for_reaction(author, msg, client, admin_list):
    numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    while True:
        res, user = await client.wait_for('reaction_add',
                                          check=lambda reaction, user: reaction.emoji == '♻️' or '❌')
        if user == author or user.id in admin_list:
            if res.message.id == msg.id:
                if res.emoji == "❌":
                    await msg.delete()
                    break


async def server_status(author, ip, port, conn, channel, client, admin_list):
    # get list of all maps (as path relative to maps/)
    select_sql = """select map_path from maps"""
    map_memory = [a for b in select(conn, select_sql, ()) for a in b]

    embed, playercount = embedmaker.make_status(ip, port, map_memory)
    msg = await channel.send(embed=embed)
    await msg.add_reaction(emoji="❌")
    await msg.add_reaction(emoji="♻️")
    future = asyncio.ensure_future(wait_for_reaction(author, msg, client, admin_list))
    already_sent = False
    while not future.done():
        embed, results = embedmaker.make_status(ip, port, map_memory)
        await msg.edit(embed=embed)
        print(str(results))
        if results:
            if not already_sent:
                await channel.send(embed=results)
                already_sent = True
        else:
            already_sent = False

        await asyncio.sleep(3)
