from colorama import Fore, Back, Style
from datetime import datetime

def printlog(text):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)

async def printlog_messge(text, message, send_text):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('---\n' + Fore.CYAN + f'[{time}] ' + Style.RESET_ALL + text)
    if message and send_text:
        await message.channel.send(send_text)