from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt
import requests as rq

import time

data = ['lists', 'cards', 'checklists']
params = {'key': '637c56e248984ec499c0361ccb63f695',
'token': '44162f9fa00913303974d79d1151c3414ee0d9978f2e6720ebff65adf5afe3bf'}

def fn(arg):
    return rq.request('GET', f'https://api.trello.com/1/boards/62221524f3b7441300da7a88/{arg}', params=params)

def multi(arg):
    with ThreadPoolExecutor(100) as executor:
        res = executor.submit(fn, arg)
    return res.result()

start = time.perf_counter()
res = []
for arg in data:
    res.append(multi(arg))

for r in res:
    print(r)

end = time.perf_counter()
print(end-start)