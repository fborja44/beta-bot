import traceback
from datetime import datetime

from colorama import Back, Fore, Style
from discord import TextChannel


def printlog(text: str, e: Exception = None):
    """A utility function to print a full log message to console.

    Args:
        text (str): The log message.
        e (Exception, optional): An error exception to print. Defaults to None.
    """
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # time w/o ms
    print("---\n" + Fore.CYAN + f"[{time}] " + Style.RESET_ALL + text)
    if e:
        traceback.print_exc()


async def printlog_msg(
    text: str, send_text: str, channel: TextChannel, e: Exception = None
):
    """A utility function to print a full log message to console and send a message in Discord.

    Args:
        text (str): The log message.
        send_text (str): The message to send in Discord.
        channel (TextChannel): The Discord channel to send the message.
        e (Exception, optional): An error exception to print. Defaults to None.
    """
    printlog(text, e)
    if channel and send_text:
        await channel.send(send_text)
