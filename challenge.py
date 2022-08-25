from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import challonge
import mdb
import re

# match.py
# Bracket matches