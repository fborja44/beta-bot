from datetime import datetime

def printlog(text):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('[{0}] '.format(time) + text)

def printdate():
    time = datetime.now().strftime("%A, %B %d, %Y %I:%M %p") # time w/o ms
    print('[{0}] '.format(time))

printdate()