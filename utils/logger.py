from colorama import Fore, Back, Style
from datetime import datetime
from discord import TextChannel
import traceback

def printlog(text: str, e: Exception = None):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)
    if e:
        traceback.print_exc()

async def printlog_msg(text: str, send_text: str, channel: TextChannel, e: Exception = None):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)
    if e:
        traceback.print_exc()
    if channel and send_text:
        await channel.send(send_text)