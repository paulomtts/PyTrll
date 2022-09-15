from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from functools import partial
from threading import Thread

import requests as rq
from datetime import datetime as dt
import httpx as hx
import itertools
import json
import time
import os

data = [('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ('Paulo', 33), ('Stela', 27), ('Laura', 27), ]

def fn(name, age):
    # name = tup[0]
    # age = tup[1]
    print(name, age, dt.now().time())
    time.sleep(1)

start = time.perf_counter()
with ThreadPoolExecutor(100) as executor:
    for args in data:
        new_fn = partial(fn, args[0])
        executor.map(new_fn, (args[1],))

# fn(*data[0])
# fn(*data[1])
# fn(*data[2])

end = time.perf_counter()
print(end-start)