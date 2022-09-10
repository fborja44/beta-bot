from discord import Member
from dotenv import load_dotenv
import os

# common.py

load_dotenv()

CHALLONGE_USER = os.getenv('CHALLONGE_USER')
CHALLONGE_KEY = os.getenv('CHALLONGE_KEY')
MONGO_ADDR = os.getenv('MONGO')
TOKEN = os.getenv('TOKEN')

BRACKETS = 'brackets'
CHALLENGES = 'challenges'
GUILDS = 'guilds'
MATCHES = 'matches'

ICON = 'https://static-cdn.jtvnw.net/jtv_user_pictures/638055be-8ceb-413e-8972-bd10359b8556-profile_image-70x70.png'
IMGUR_CLIENT_ID = os.getenv('IMGUR_ID')
IMGUR_URL = 'https://api.imgur.com/3'

MAX_ENTRANTS = 24