# MapSearch

This is an improved version of the Discord Search bot for Digital Paintball 2 maps at https://github.com/aapokaapo/MapSearch currently running
at the official Paintball 2 Discord. Its web-end is currently hosted at http://whoa.ml/dpfiles/map_browser.php

The original bot supported searching for maps, the trivia game
 (a map guessing game based on renderings using https://github.com/lennart-g/BSP-Hacking),
 adding mapshots and tags to maps and a live broadcast of matches.
 
 This version uses SQLite for quicker accessing of map information, determines all files used by a map and uses
 the python module Watchdog to monitor the file system for added or deleted files and updates the
 database accordingly.
 
 **Requirements**
 
 Next to official python3 modules like discord, this project uses code from the following repos:
 - https://github.com/mRokita/DPLib (the required files are included in this repo)
 - https://github.com/lennart-g/BSP-Hacking
 - https://github.com/lennart-g/blender-md2-importer
 
 **Discord commands**
 
     **Admin commands:**
    `!reloadmaps` - Updates the map data (in comparison to the file system)
    `!reloadrequirements` - Reloads tables for map requirements and specified if they're provided

    **User commands:**
    `!mapshot` `<map name>` (attached image) - Adds attached image as the maps mapshot
    `!addtag` `<map name>` `<tags>` - Adds tags for the map, separate tags with whitespace
    `!deltag` `<map name>` `<tags>` - Removes tags from the map, separate tags with whitespace

    **Public commands:**
    `!updatefiles` - Updates if required files are provided by the server
    `!files` - lists how many maps are on the server and how many of their required files are provided or not
    
    *Map Browser*
    `!mapsearch` `<keyword>` - Returns a list of maps with the keyword in either name or message
    `!mapinfo` `<map name>` - Returns map information (path, message, tags etc.)
    
    *Broadcast*
    `!broadcast` - shows a list of populated servers
    `!scores` `<ip>:<port>` - broadcast the server specified with direct ip and port
    
    *Trivia*
    `!trivia` - starts a trivia instance, if nobody answers correctly in 50 messages, closes itself
    `pass` - passes the question
    `hint` - gives the answer letter by letter
    `quit` - closes all trivia instances
    """

**How to use**
- Enter the game file paths of your server as well as the bot settings in config.py
- Launch the Bot using `screen -AmdS <screen name> python3 <path/to/MapSearch.py>`
- Launch the Watchdog using `screen -AmdS <screen name> python3 <path/to/pball_watchdog.py>`