import challonge
import os
import re
import requests
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

# def printlog(text):
#     time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
#     print('[{0}] '.format(time) + text)

# def printdate():
#     time = datetime.now().strftime("%A, %B %d, %Y %I:%M %p") # time w/o ms
#     print('[{0}] '.format(time))

# time_re = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9] ([AaPp][Mm])$')
# time_re2 = re.compile(r'([1-9]|0[1-9]|1[0-2]) ([AaPp][Mm])$')

# test = "$bracket create Test Bracket 10:30 PM   "
# test2 = "$bracket create Test Bracket 10 PM   "

# print(time_re2.search("10 PM").group())

# print(time_re.search(test.strip()).span())
# print(date.today())
# print(datetime.now())
# print(datetime.strptime('{0} 10:30 PM'.format(date.today()), '%Y-%m-%d %H:%M %p'))
# time = datetime.now() + timedelta(hours=1)
# print(time)

# match = time_re.search(test.strip()).span()

# argv = test[:match[0]].split()
# print(argv)

CHALLONGE_USER = os.getenv('CHALLONGE_USER')
CHALLONGE_KEY = os.getenv('CHALLONGE_KEY')

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)

tournament = challonge.tournaments.create(name="Test", url=None, tournament_type='double elimination', start_at=datetime.now(), show_rounds=True, private=True)
print(tournament)

challonge.participants.create(tournament['id'], "Billy Bob")

# response = challonge.tournaments.destroy(tournament['id'])
# print(response)