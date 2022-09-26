from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from random import randint

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

    def __init__(self, key: str, token: str, threads: int = None, chunk_size: int = 30, api_interval: float = 0.5) -> None:
        super().__init__()
        self.__headers          :dict   = {"Accept": "application/json"}
        self.__query            :dict   = {'key'     : key,
                                           'token'   : token}
        self.__request_pool     :dict   = {}
        self.__threads          :int    = os.cpu_count() + 4
        self.__chunk_size       :int    = chunk_size
        self.__api_interval     :float  = api_interval

        if threads != None:
            self.__threads = threads

        if chunk_size != None:
            self.__chunk_size = chunk_size

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(pools={self.__request_pool!r}, chunk_size={self.__chunk_size!r})'

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
    def chunk_size(self):
        return self.__chunk_size

    @property
    def api_interval(self):
        return self.__api_interval

    # METHODS ##############################################################   
    def queue(self, key: str, func, *args, **kwargs):
        """Queue function to be executed concurrently. Functions are stored in
        a list within a dictionary key."""

        if args == None: args = []
        if kwargs == None: kwargs = {}
        if self.__request_pool.get(key, None) is None:
            self.__request_pool[key] = []

        self.__request_pool[key].append((func, args, kwargs))

    def execute(self, key: str):
        """Concurrently execute functions in a queue. Execution will be done in
        chunks, but returned as a list of responses, sorted by queueing order."""

        def split(lst, chunk_size):
            for i in range(0, len(lst), chunk_size):
                yield lst[i:(i + chunk_size)]

        pool_lst = list(split(self.__request_pool[key], self.__chunk_size))
        response_lst = []

        for pool in pool_lst:
            with ThreadPoolExecutor(self.__threads) as executor:
                for (fn, args, kwargs) in pool:
                    response_lst.append(executor.submit(fn, *args, **kwargs))
            
            time.sleep(self.__api_interval)
        
        self.__request_pool.pop(key)
            
        return [response.result() for response in response_lst]


class BaseObject(ABC):
    """A generic blueprint for Trello objects."""
    
    @abstractmethod
    def __init__(self, app: App, id: str, prefix: str):   
        self.__app          :App       = app
        self.__prefix       :str       = prefix

        self.__id           :str       = id
        self.__json         :json      = None


    def __getitem__(self, *tup: str):
        """Contains search mechanisms."""
        args = tup[0]

        # Single arguments ##############
        if not isinstance(tup[0], tuple):
            
            if not isinstance(args, (list, str)):
                raise TypeError(f"Single arguments can only be {str.__class__} or {list.__class__}.")
            # Single string: [str] -> str
            if isinstance(args, str):
                return self.json[args]

            # List of JSONs: [list] -> list[json, ...]
            elif isinstance(args, list) and all(isinstance(key, (Board, List, Card)) for key in args[1:]):
                return [obj.json for obj in args]
        
        # Multiple arguments ############
        else:
            
            # [str, str, str, ...]
            if all(isinstance(el, str) for el in tup[0]):
                return json.dumps({key: self.json[key] for key in tup[0]})

            container: list = args[0]
            if not isinstance(container, (list, dict, json)):
                raise TypeError(f"Expected {list.__class__} for CONTAINER, but got {container.__class__}")
            if isinstance(container, list) and not all(isinstance(cont, (List, Card, Checklist)) for cont in container):
                raise TypeError(f"All ITEMS in a container must be of type {List.__class__}, {Card.__class__} or {Checklist.__class__}.")            
            
            
            match_dict: dict = args[1]
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
            

            keys: list = [el for el in args[pos:]]
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
        """URL: ({prefix} | {alt_prefix}) /\t({body} | {id}/{body})\t/"""

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
        Example: when called from a Board object, this method will setup self and all lists belonging to
        that board."""

        num = randint(1000, 10000)
        if f'{self.id}_family' in self.app.request_pool.keys():
            raise ValueError(f'{self.id}__family__{num} is an invalid key for the queue. Please remove it from the queue before executing this method.')

        fnc_sw = {'boards': self.get_lists, 
                  'lists':  self.get_cards, 
                  'cards': self.get_checklists}

        self.app.queue(f'{self.id}__family__{num}', self.get_self)
        self.app.queue(f'{self.id}__family__{num}', fnc_sw[self.__prefix])
        self.app.execute(f'{self.id}__family__{num}')
            
        obj_sw = {'boards': self.lists, 
                  'lists':  self.cards, 
                  'cards': self.checklists}

        for obj in obj_sw[self.__prefix]:
            self.app.queue(f'{self.id}__family__{num}', obj.get_self)
        self.app.execute(f'{self.id}__family__{num}')

    # REQUESTS #############################################################
    def get_self(self):
        """Acquire a JSON representing this object from Trello. \nURL: varies according to calling object."""
        response = self._request('GET', self.id)
        self.__json = response.json()
        return response

    def update_self(self, query: dict=None):
        """Update an object in Trello. \nURL: varies according to calling object."""
        response = self._request('PUT', self.id, query=query)
        self.__json = response.json()
        return response


class Board(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'boards')
        self.__lists = CustomList()
        self.__cards = CustomList()
        self.__checklists = CustomList()

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
        """Acquire Lists from a board. \nURL: /1/boards/{id}/lists"""
        response = self._request('GET', self.id, 'lists')
        self.__lists = CustomList([List(self.app, json['id']) for json in response.json()])
        return response
    
    def get_cards(self):
        """Acquire Cards from a board or list in Trello. \nURL: /1/boards/{id}/cards"""
        response = self._request('GET', self.id, 'cards')
        self.__cards = CustomList([Card(self.app, json['id']) for json in response.json()])
        return response

    def get_checklists(self):
        """Acquire Checklists from a board. \nURL: /1/boards/{id}/checklists"""
        response = self._request('GET', self.id, 'checklists')
        self.__checklists = CustomList([Checklist(self.app, json['id']) for json in response.json()])
        return response


class List(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'lists')
        self.__cards = CustomList()

    # PROPERTIES ###########################################################    
    @property
    def cards(self):
        return self.__cards

    # REQUESTS #############################################################
    def get_cards(self):
        """Acquire Cards from a board or list in Trello. \nURL: /1/lists/{id}/cards"""
        response = self._request('GET', self.id, 'cards')
        self.__cards = CustomList([Card(self.app, json['id']) for json in response.json()])
        return response

    def create_card(self, title: str = '', description: str = '', start_date: str = '', due_date: str = '', pos: str = ''):
        """Create a card in a list.\nURL: /1/cards"""
        query = {'idList':  self.id,
                 'name':    title, 
                 'desc':    description,
                 'start':   start_date,
                 'due':     due_date,
                 'pos':     pos}

        response = self._request('POST', alt_prefix='cards', query=query)

        card_id = response.json()['id']
        self.__cards.append(Card(self.app, card_id))

        return response


class Card(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'cards')
        self.__checklists = CustomList()

    # PROPERTIES ###########################################################    
    @property
    def checklists(self):
        return self.__checklists


class Checklist(BaseObject):
    def __init__(self, app: App, id: str):
        super().__init__(app, id, 'checklists')
        self.__checkitems = CustomList()

    # PROPERTIES ###########################################################    
    @property
    def checkitems(self):
        return self.__checkitems

class CustomList():
    """A custom list for the Trello objects. Facilitates __getitem__ syntax in
    other classes."""

    types = [Board, List, Card, Checklist]
    
    def __init__(self, data: list = None) -> None:
        if data is None:
            data = []
        elif not all(type(obj) in self.types for obj in data):
            raise TypeError(f'Can only accept objects of the following types: {self.types!r}')

        self.__data = data

    def __repr__(self):
        return repr(self.__data)

    def __getitem__(self, entry):
        if isinstance(entry, int):
            return self.__data[entry]
        
        elif isinstance(entry, str):
            return tuple(obj.json[entry] for obj in self.__data)
        
        elif isinstance(entry, dict):
            results = []

            for obj in self.__data:
                appnd = True
                for key, values in entry.items():
                    if obj.json[key] not in values:
                        appnd = False
                if appnd:
                    results.append(obj.json)

            return results
        
        elif isinstance(entry, tuple):
            
            if all(isinstance(obj, str) for obj in entry):
                return [tuple(obj.json[item] for item in entry) for obj in self.__data]
            
            elif isinstance(entry[0], dict) and all(isinstance(obj, str) for obj in entry[1:]):
                
                results = []

                for obj in self.__data:
                    appnd = True
                    for key, values in entry[0].items():
                        if obj.json[key] not in values:
                            appnd = False
                    if appnd:
                        results.append(obj.json)

                return [{key:val for key, val in obj.items() if key in entry[1:]} for obj in results]
            else:
                raise TypeError("Incorrect mix of types.")

    def __setitem__(self, entry, val):
        if type(entry) is int:
            if type(val) in self.types:
                self.__data[entry] = val
        else:
            raise TypeError("Entry must be an integer.")

    def __delitem__(self, item):
        del self.__data[item]

    # METHODS ##############################################################
    def insert(self, index, val):
        if type(val) in self.types:
            self.__data.insert(index, val)
        else:
            raise TypeError(f'Cannot insert {type(val)} object.')

    def append(self, val):
        if type(val) in self.types:
            self.insert(len(self.__data), val)
        else:
            raise TypeError(f'Cannot insert {type(val)} object.')
    
    def pop(self, index):
        return self.__data.pop(index)

