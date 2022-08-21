from colorama import Fore, Back, Style
from datetime import datetime
from discord import TextChannel

def printlog(text: str, e: Exception = None):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)
    if e:
        print(e)

async def printlog_msg(text: str, send_text: str, channel: TextChannel):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)
    if channel and send_text:
        await channel.send(send_text)