# Developer: Paulo Mattos
# API: https://developer.atlassian.com/cloud/trello/rest/
#
# ##############################################################################################
#
# The goal of this module is NOT to precisely reflect Trello's API, but rather to provide a
# simple set of tools with which to allow python users to easily read and manipulate Trello.
#
# This module uses enviroment variables to acquire the Trello key & token. Be sure
# to set them before instantiating any objects. Their names are 'trello_key' and 
# 'trello_token'.
#
#                                   ### METHOD RATIONALE ###
#
# PROPERTIES:       single-purpose | private | properties of an object
# PRIVATE:          single-purpose | private | only accessible to itself or its heirs
# METHODS:          single-purpose | public  | general tasks
# SCRIPT METHODS:   multi-purpose  | public  | provided for convenience
# REQUESTS:         single-purpose | public  | perform requests on the Trello API
#
#                                   ### OBJECT PROPERTIES ###
#
# All objects possess the following properties:
# - json:       a JSON acquire from the Trello API corresponding to this object's id property.
# - id:         an identification string from Trello, this is provided for conveniency
#
# There are no setter properties for any objects. Any setting of variables must be done through 
# the appropriate request, thus ensuring that any data in a property in all likelihood originated 
# from Trello. Python does not enforce property privacy, therefore we cannot truly prevent a 
# developer from meddling with this system.
# #############################################################################################

HELP = """
# Simple object setup
>>> brd = Board('id_number_here')
>>> brd.get_self()
>>> brd.dump(brd.json)

>>> brd.get_lists()
>>> print(brd.lists)

>>> for lst in brd.lists:
>>>     lst.get_self()

# Queueing
>>> brd.queue_url(brd.id, 'lists')
>>> brd.queue_url(brd.id, 'cards')
>>> print(brd.batch)
>>> print(brd.run_batch().json())
>>> print(brd.batch)


# [str] -> str
>>> brd['name']

# [str, ...] -> json{str: val, str: val, ...}
>>> brd['name', 'id']

# [list] -> list[json, ...]
>>> brd[brd.lists]

# [list, str, ...] -> list[json, ...]
>>> brd[brd.lists, 'name', 'id'] 

# [list, (str, str)]   |   [list, (str, [str, ...])] -> list[json, ...]
>>> brd[brd.lists, {'name': ['PEDIDOS', 'dev_list']}]

# [list, (str, str), str, ...]   |   [list, (str, [str, ...]), str, ...] -> list[json, ...]
>>> brd[brd.lists, {'name': ['PEDIDOS', 'dev_list']}, 'name', 'id']
"""

from abc import ABC, abstractmethod

import requests as rq
import itertools
import json
import os


class TrelloAPIError(Exception):
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
        message = TrelloAPIError.STATUS_CODES.get(response.status_code, 'Unknown status code.') + f' Status Code: {response.status_code}.'
        super().__init__(message)


class TrelloBaseObject(ABC):
    """A generic blueprint Trello objects."""
    
    @abstractmethod
    def __init__(self, id: str, prefix: str):        
        self.__id           :str      =id
        self.__json         :json     =None
        self.__prefix       :str      =prefix

        self.__key          :str      =os.environ['trello_key']
        self.__token        :str      =os.environ['trello_token']
        self.__query        :dict     ={'key':      self.__key,
                                        'token':    self.__token}
        
        self.__batch        :list     =[]
        

    def __getitem__(self, *tup: str):
        """Contains search mechanisms."""

        # Single arguments ##############
        if not isinstance(tup[0], tuple):
            
            arg = tup[0]
            if not isinstance(arg, (list, str)):
                raise TypeError(f"Single arguments can only be {str.__class__} or {list.__class__}.")

            # [str] -> str
            if isinstance(arg, str):
                return self.json[arg]

            # [list] -> list[json, ...]
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
    def json(self):
        return self.__json

    @property
    def id(self):
        return self.__id

    @property
    def batch(self):
        return self.__batch


    # PRIVATE ##############################################################
    def _add_params(self, **params):
        self.__query.update(params)

    def _del_params(self, keys: list):
        for key in keys:
            self.__query.pop(key, None)

    def _build_url(self, body: str) -> str:
        return f'https://api.trello.com/1/{body}'

    def _request(self, method: str, id: str = '', body: str = '', query: dict = None, **params):
        if body == 'batch':
            url = self._build_url(f'batch')
        else:
            if id == '': 
                slash = ''
            else:
                slash = '/'
            url = self._build_url(f'{self.__prefix}/{id}{slash}{body}')

        if not query: 
            query = self.__query
        if params:
            query.update(params)

        response = rq.request(method, url, params=query)
       
        if response.status_code != 200:
            raise TrelloAPIError(response)
        return response
    

    # METHODS ##############################################################   
    def help(self):
        """Print usefull object usage information."""
        print(HELP)
    
    def clear_batch(self):
        """Clear up the batch."""
        self.__batch = []
    
    def queue_url(self, id: str='', body: str=''):
        """Store an URL in the batch list, for later execution."""
        self.__batch.append(f'/{self.__prefix}/{id}/{body}')
    
    def run_batch(self):
        """Execute the current batch of URLs as requests."""
        self._add_params(urls=','.join(self.__batch))
        response = self._request("GET", body='batch', params=self.__query)
        self._del_params('urls')
        
        self.clear_batch()
        return response        

    def dump(self, js):
        """Pretty print a json."""
        print(json.dumps(js, indent=4, sort_keys=False))

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


class Board(TrelloBaseObject):
    def __init__(self, id: str):
        super().__init__(id, 'boards')
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
        self.__lists = [List(json['id']) for json in response.json()]
        return response
    
    def get_cards(self):
        """Acquire Cards from a board or list in Trello."""
        response = self._request('GET', self.id, 'cards')
        self.__cards = [Card(json['id']) for json in response.json()]
        return response

    def get_checklists(self):
        """Acquire Checklists from a board.."""
        response = self._request('GET', self.id, 'checklists')
        self.__checklists = [Checklist(json['id']) for json in response.json()]
        return response


class List(TrelloBaseObject):
    def __init__(self, id: str):
        super().__init__(id, 'lists')
        self.__cards = None

    # PROPERTIES ###########################################################    
    @property
    def cards(self):
        return self.__cards


class Card(TrelloBaseObject):
    def __init__(self, id: str):
        super().__init__(id, 'cards')
        self.__checklists = None

    # PROPERTIES ###########################################################    
    @property
    def checklists(self):
        return self.__checklists


class Checklist(TrelloBaseObject):
    def __init__(self, id: str):
        super().__init__(id, 'checklists')
        self.__checkitems = None

    # PROPERTIES ###########################################################    
    @property
    def checkitems(self):
        return self.__checkitems
