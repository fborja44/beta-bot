from datetime import datetime

def printlog(text):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # time w/o ms
    print('[{0}] '.format(time) + text)

printlog("Hello World!")