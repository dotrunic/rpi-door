import datetime

stash = []

def log(message):
    entry = f"{datetime.datetime.now()} - {message}"
    print(entry)
    stash.append(entry)
