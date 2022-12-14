from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod

import requests as rq
import itertools
import json
import time
import os

class APIError(Exception):
    """The Trello exception class."""

    STATUS_CODES = {
        400: "Bad Request - The request does not have the required fields, or the fields the request has are invalid in some way.",
        401: "Unauthorized - The request has invalid credentials, or no credentials when credentials are required, or the user doesn't have permissions to do that.",
        403: "Forbidden - API will not allow that in this case. Like, the user can't add another checklist if they have too many.",
        404: "Not Found - We don't have a route registered there, e.g. it's not possible to GET /1/cards, or POST /1/elephants. Or the model the request is trying to operate on couldn't be found. Or some nested resource can't be found.",
        409: "Conflict - The request doesn't match our state in some way.",
        429: "Too Many Requests - API wants your application to send fewer requests. Because for example the user is violating a rate limit by sending too many requests per time period.",
        449: "Sub-Request Failed - API was unable to process every part of the request.",
        500: "Internal Server Error - Something went wrong and we don't know what.",
        503: "Service Unavailable - Something is down that should be up. Our load balancers might return this if we're down. And we return it if something we're relying on to handle the request successfully isn't answering.",
        504: "Gateway Timeout - We couldn't handle the GET request within our time limit (30s).",
    }

    def __init__(self, response: rq.Response) -> None:
        message = APIError.STATUS_CODES.get(response.status_code, 'Unknown status code.') + f' Status Code: {response.status_code}.'
        super().__init__(message)


class App():
    """Hold the query dictionary and handle concurrent requests."""

    def __init__(self, key: str, token: str, threads: int = None, chunk_size: int = None, api_interval: float = 0.5) -> None:
        super().__init__()
        self.__headers          :dict   = {"Accept": "application/json"}
        self.__query            :dict   = {'key'     : key,
                                           'token'   : token}
        self.__request_pool     :list   = [[],]
        self.__current_pool     :int    = 0
        self.__chunk_size       :int    = chunk_size
        self.__api_interval     :float  = api_interval

        if threads != None:
            self.threads = threads
        else:
            self.threads = os.cpu_count() + 4

        if chunk_size != None:
            self.__chunk_size = chunk_size
        else:
            self.__chunk_size = 10

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(chunk_size={self.__chunk_size!r}, current_pool={self.__current_pool!r}, pool_lst={self.__request_pool!r})'

    @property
    def headers(self):
        return self.__headers

    @property
    def query(self):
        return self.__query

    @property
    def request_pool(self):
        return self.__request_pool

    @property
    def current_pool(self):
        return self.__current_pool

    @property
    def chunk_size(self):
        return self.__chunk_size

    @property
    def api_interval(self):
        return self.__api_interval

    # METHODS ##############################################################   
    def queue(self, func, *args, **kwargs):
        """Queue function to be executed concurrently. Queues have a maximum size,
        and whenever a limit is reached, a new chunk will be created."""

        if args == None: args = []
        if kwargs == None: kwargs = {}

        if len(self.__request_pool) == 0:
            self.__request_pool.append([])

        if len(self.__request_pool[self.__current_pool]) == self.__chunk_size:
            self.__request_pool.append([])
            self.__current_pool += 1

        self.__request_pool[self.__current_pool].append((func, args, kwargs))

    def execute(self, pool_number: int = None):
        """Concurrently execute functions in the queue. If a pool number is provided,
        will execute only the functions in that pool, otherwise it will execute all
        functions in all pools."""

        if pool_number is None:
            response_lake = []
            
            for pool in self.__request_pool:
                response_lst = []
                
                with ThreadPoolExecutor(self.threads) as executor:
                    for (fn, args, kwargs) in pool:
                        response_lst.append(executor.submit(fn, *args, **kwargs))
                    response_lake.append(response_lst)
                    executor
                time.sleep(self.api_interval)
            
            self.__request_pool = []
            self.__current_pool = 0
            
            result = response_lake

        else:
            with ThreadPoolExecutor(self.threads) as executor:
                response_lst = []

                for (fn, args, kwargs) in self.__request_pool[pool_number]:
                    response_lst.append(executor.submit(fn, *args, **kwargs))
                
                self.__request_pool.pop(pool_number)
                self.__current_pool = len(self.__request_pool)-1
                
            result = response_lst
           
        if all(isinstance(obj, list) for obj in result):
            result = [[res.result() for res in lst] for lst in result]
        else:
            result = [res.result() for res in result]
    
        return result


class BaseObject(ABC):
    """A generic blueprint for Trello objects."""
    
    @abstractmethod
    def __init__(self, app: App, id: str, prefix: str):   
        self.__app          :App       = app

        self.__id           :str       = id
        self.__json         :json      = None
        self.__prefix       :str       = prefix


    def __getitem__(self, *tup: str):
        """Contains search mechanisms."""

        # Single arguments ##############
        if not isinstance(tup[0], tuple):
            
            arg = tup[0]
            if not isinstance(arg, (list, str)):
                raise TypeError(f"Single arguments can only be {str.__class__} or {list.__class__}.")

            # Single string: [str] -> str
            if isinstance(arg, str):
                return self.json[arg]

            # List of JSONs: [list] -> list[json, ...]
            elif isinstance(arg, list) and all(isinstance(key, (Board, List, Card)) for key in arg[1:]):
                return [obj.json for obj in arg]
        
        # Multiple arguments ############
        else:
            
            # [str, str, str, ...]
            if all(isinstance(el, str) for el in tup[0]):
                return json.dumps({key: self.json[key] for key in tup[0]})

            container: list = tup[0][0]
            if not isinstance(container, (list, dict, json)):
                raise TypeError(f"Expected {list.__class__} for CONTAINER, but got {container.__class__}")
            if isinstance(container, list) and not all(isinstance(cont, (List, Card, Checklist)) for cont in container):
                raise TypeError(f"All ITEMS in a container must be of type {List.__class__}, {Card.__class__} or {Checklist.__class__}.")            
            
            
            match_dict: dict = tup[0][1]
            if isinstance(match_dict, dict):
                pos = 2
                if not all(isinstance(k, str) for k in match_dict.keys()):
                    raise TypeError(f"All MATCH KEYS must be of type {str.__class__}.")
                if not all(isinstance(k, list) for k in match_dict.values()):
                    raise TypeError(f"All MATCH VALUES must be of type {list.__class__}.")
                
                values = []
                for lst in itertools.chain(match_dict.values()):
                    values.extend(lst)
                if not all(isinstance(k, str) for k in values):
                    raise TypeError(f"All ELEMENTS in a match's list of values must be of type {str.__class__}.")
            else:    
                pos = 1
                match_dict = {}
            

            keys: list = [el for el in tup[0][pos:]]
            if not all(isinstance(k, str) for k in keys):
                raise TypeError(f'All KEYS must be of type {str.__class__}.')


            # See if an object's json fits all the criteria
            def _fit(object, matches: dict):
                for key, val_lst in matches.items():
                    if object.json[key] not in val_lst:
                        return False
                return object.json

            # Perform searches, if any
            if match_dict != {}:
                matches = []
                for object in container:
                    matches.append(_fit(object, match_dict))
                
                container = list(filter(None, matches))

            if keys != []:
                return [{k:object[k] for k in keys} for object in container]
            return container

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.__id!r})'

    # PROPERTIES ###########################################################    
    @property
    def id(self):
        return self.__id
    
    @property
    def json(self):
        return self.__json

    @property
    def app(self):
        return self.__app

    # PRIVATE ##############################################################
    def _build_url(self, body: str) -> str:
        return f'https://api.trello.com/1/{body}'

    def _request(self, method: str, id: str = '', body: str = '', alt_prefix: str = None, query: dict = None, **params):
        slash = ''
        if id != '':
            slash = '/'
        
        if alt_prefix == None:
            prefix = self.__prefix
        else:
            prefix = alt_prefix

        url = self._build_url(f'{prefix}/{id}{slash}{body}')


        if query == None: 
            query = self.app.query
        else:
            query.update(self.app.query)

        if params:
            query.update(params)

        response = rq.request(method, url, headers=self.app.headers, params=query)

        if response.status_code != 200:
            raise APIError(response)
        return response

    
    # METHODS ##############################################################   
    def dump(self, js = None):
        """Pretty print a json."""
        
        if js == None:
            js = self.json
        
        if not isinstance(js, list):
            js = [js]

        for obj in js:
            print(json.dumps(obj, indent=4, sort_keys=False))

    # SCRIPT METHODS #######################################################
    def set_family(self):
        """Fully setup  self and all objects belonging to the layer hierarchically below this object.
        Example: when called from a Board object, this method will setup all lists belonging to
        that board."""

        fnc_sw = {'boards': self.get_lists, 
                  'lists':  self.get_cards, 
                  'cards': self.get_checklists}
        
        self.app.queue(self.get_self)
        self.app.queue(fnc_sw[self.__prefix])
        self.app.execute()

        obj_sw = {'boards': self.lists, 
                  'lists':  self.cards, 
                  'cards': self.checklists}

        for obj in obj_sw[self.__prefix]:
            self.app.queue(obj.get_self)
        self.app.execute()

    # REQUESTS #############################################################
    def get_self(self):
        """Acquire a JSON representing this object from Trello."""
        response = self._request('GET', self.id)
        self.__json = response.json()
        return response

    def update_self(self, query: dict=None):
        """Update an object in Trello."""
        response = self._request('PUT', self.id, query=query)
        self.__json = response.json()
        return response


class Board(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'boards')
        self.__lists = None
        self.__cards = None
        self.__checklists = None

    # PROPERTIES ###########################################################    
    @property
    def lists(self):
        return self.__lists
    
    @property
    def cards(self):
        return self.__cards
    
    @property
    def checklists(self):
        return self.__checklists
    
    # REQUESTS #############################################################
    def get_lists(self):
        """Acquire Lists from a board."""
        response = self._request('GET', self.id, 'lists')
        self.__lists = [List(self.app, json['id']) for json in response.json()]
        return response
    
    def get_cards(self):
        """Acquire Cards from a board or list in Trello."""
        response = self._request('GET', self.id, 'cards')
        self.__cards = [Card(self.app, json['id']) for json in response.json()]
        return response

    def get_checklists(self):
        """Acquire Checklists from a board.."""
        response = self._request('GET', self.id, 'checklists')
        self.__checklists = [Checklist(self.app, json['id']) for json in response.json()]
        return response


class List(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'lists')
        self.__cards = None

    # PROPERTIES ###########################################################    
    @property
    def cards(self):
        return self.__cards


    def get_cards(self):
        """Acquire Cards from a board or list in Trello."""
        response = self._request('GET', self.id, 'cards')
        self.__cards = [Card(self.app, json['id']) for json in response.json()]
        return response

    def create_card(self, title: str, description: str = '', start_date: str = '', due_date: str = '', pos: str = 'bottom'):
        """Create a card in a list."""
        query = {'idList':  self.id,
                 'name':    title, 
                 'desc':    description,
                 'start':   start_date,
                 'due':     due_date,
                 'pos':     pos}

        response = self._request('POST', alt_prefix='cards', query=query)

        #####
        card_id = response.json()['id']

        self.__cards.append(Card(self.app, card_id))
        #####

        return response


class Card(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'cards')
        self.__checklists = None

    # PROPERTIES ###########################################################    
    @property
    def checklists(self):
        return self.__checklists


class Checklist(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'checklists')
        self.__checkitems = None

    # PROPERTIES ###########################################################    
    @property
    def checkitems(self):
        return self.__checkitems

key = '637c56e248984ec499c0361ccb63f695'
token = '44162f9fa00913303974d79d1151c3414ee0d9978f2e6720ebff65adf5afe3bf'
brd_id = '62221524f3b7441300da7a88'

start = time.perf_counter()

app = App(key, token, api_interval=0.0)
brd = Board(app, brd_id)

brd.set_family()
brd.lists[0].get_cards()
for i in range(1, 10):
    app.queue(brd.lists[0].create_card, f'Card {i}', pos=f'{i}')
app.execute()
brd.set_family()

brd.get_cards()
print(brd.cards)
print()
print(brd.lists[0].cards)

end = time.perf_counter()
print(f'{end-start:.4f} seconds')