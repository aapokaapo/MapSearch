from utils import send
import asyncio
import os
import secrets
import shutil
import random
import embedmaker
from db_io import *
from collections import deque
from config import topshot_path, trivia_path

async def trivia(conn, bot, ctx) -> None:
    """
    picks map, creates copy with hash name and starts guessing game
    :param conn:
    :param bot:
    :param ctx:
    :return:
    """
    select_sql = """select map_path from maps"""
    map_memory = [a for b in select(conn, select_sql, ()) for a in b]

    seen_maps = deque(maxlen=50)
    chosen_map = None
    while True:
        current_map = random.choice(map_memory)
        if current_map.split("/")[0] in ["", "beta"]:
            if current_map not in seen_maps and os.path.isfile(topshot_path + current_map + ".jpg"):
                print("exists")
                seen_maps.append(current_map)
                chosen_map = current_map
                break
    print(chosen_map)
    if chosen_map:
        random_file_name = secrets.token_hex(16)
        if not os.path.exists(trivia_path):
            os.makedirs(trivia_path)
        clear_dir(trivia_path)
        shutil.copyfile(topshot_path + chosen_map + ".jpg", trivia_path + random_file_name + ".jpg")
        channel = ctx.channel if hasattr(ctx, "channel") else ctx
        msg = await channel.send(embed=embedmaker.trivia(random_file_name))
        task = asyncio.ensure_future(wait_for_answer(msg, current_map.split("/")[-1], bot, conn, ctx))

        def _log_error(fut):
            exc = fut.exception()
            if exc:
                print(f"Trivia error: {exc!r}")

        task.add_done_callback(_log_error)

async def wait_for_answer(msg, map_name, bot, conn, ctx) -> None:
    """
    Guessing loop for running trivia game
    :param msg:
    :param map_name:
    :param bot:
    :param conn:
    :param ctx:
    :return:
    """
    channel = ctx.channel if hasattr(ctx, "channel") else ctx
    x = 0
    i = 0
    hint = ""
    while True:
        message = await bot.wait_for('message', check=lambda m: m.channel.id == msg.channel.id)
        x += 1
        if map_name in message.content.lower().split():
            await channel.send("Correct! The answer was {}".format(map_name))
            await trivia(conn, bot, ctx)
            await asyncio.sleep(10)
            await msg.delete()
            break
        elif x == 50:
            await channel.send("Wow nobody got it right? The answer was {}. Trivia has ended.".format(map_name))
            await msg.delete()
            break
        elif message.content.lower() == "pass":
            await channel.send("The answer was {}. -10 points to {}".format(map_name, random.choice(
                ["Gryffindor", "John Cena", "your mom", "you, you idiot", "Gandalf", "DirtyTaco", "whoa", " everyone",
                 "James Bond", "Sub-Zero", "Spyro the Dragon", "BlueBalls Studios", "DPBot01"])))
            await msg.delete()
            await trivia(conn, bot, ctx)
            break
        elif message.content.lower() == "quit":
            await channel.send("Trivia has ended!")
            await msg.delete()
            break
        elif message.content.lower() == "hint":
            if i < len(map_name):
                hint += map_name[i]
            i += 1
            embed = msg.embeds[0]
            embed.clear_fields()
            embed.add_field(name="Map name", value=hint, inline=False)
            await msg.edit(embed=embed)

def clear_dir(folder: str) -> None:
    """
    Removes all contents from specified directory
    :param folder:
    :return:
    """
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))
