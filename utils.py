async def send(ctx_or_channel, content=None, **kwargs):
    """
    Send a message to either a slash-command ApplicationContext or a raw channel.
    The first call on an ApplicationContext uses respond(); subsequent calls use channel.send().
    """
    if hasattr(ctx_or_channel, "respond"):
        if not getattr(ctx_or_channel, "_responded", False):
            await ctx_or_channel.respond(content, **kwargs)
            ctx_or_channel._responded = True
        else:
            await ctx_or_channel.channel.send(content, **kwargs)
    else:
        await ctx_or_channel.send(content, **kwargs)
