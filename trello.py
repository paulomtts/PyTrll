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
# - children:   a list of instances of children objects (refer to the Trello Hierarchy)
# - id:         an identification string from Trello, this is provided for conveniency
#
# There are no setter properties for any objects. Any setting of variables must be done through 
# the appropriate request, thus ensuring that any data in a property in all likelihood originated 
# from Trello. Python does not enforce property privacy, therefore we cannot prevent developer 
# meddling with this system.
#  
#                              ### NAMED TUPLES NAMING CONVENTION ###
# 
# There are three functions whose returns are or include namedTuples: extract(), search() and 
# to_tuple(). The first two return generators containing namedTuples, whose names are the same
# as the calling function. The result of to_tuple() is named after the originating object, since
# it represents a fraction of it.
# ##############################################################################################

from abc import ABC, abstractmethod
from collections import namedtuple

import requests as rq
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
        self.__children     :list     =[]
        self.__prefix       :str      =prefix

        self.__key          :str      =os.environ['trello_key']
        self.__token        :str      =os.environ['trello_token']
        

    def __getitem__(self, key: str):
        return self.__json.get(key, None)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.__id!r})'

    # PROPERTIES ###########################################################    
    @property
    def json(self):
        return self.__json
    
    @property
    def children(self):
        return self.__children

    @property
    def id(self):
        return self.__id

    # PRIVATE ##############################################################  
    def _build_url(self, body: str) -> str:
        return f'https://api.trello.com/1/{body}?key={self.__key}&token={self.__token}'

    def _request(self, method: str, id: str='', body: str='', query: dict=None):
        url = self._build_url(f'{self.__prefix}/{id}/{body}')
        response = rq.request(method, url, params=query)
        
        if response.status_code != 200:
            raise TrelloAPIError(response)
        return response

    # METHODS ##############################################################
    def extract(self, json_list: list, *keys: str):
        """Extract data from a list of JSONs and return it as a generator containing namedTuples."""
        Object = namedtuple(self.extract.__name__, [*keys])
        return ((Object(*[json.get(key, None) for key in keys]) for json in json_list))
    
    def search(self, json_list: list, look_by: str, look_for: str, *keys: str):
        """Conditionally extract data from a list of JSONs and return it as a generator containing namedTuples."""
        Object = namedtuple(self.search.__name__, [*keys])
        return (Object(*[json.get(key, None) for key in keys]) for json in json_list if json[look_by] == look_for)

    def to_tuple(self, *keys):
        """Get specific data from this object's JSON and return it as a namedTuple."""
        Object = namedtuple(self.__class__.__name__.lower(), [*keys])
        return Object(*[self.json.get(key, None) for key in keys])

    # SCRIPT METHODS #######################################################
    def populate(self):
        """Populate this object with instances of it's children objects. i.e.: boards > lists"""
        switch = {'boards': ('lists', List), 'lists': ('cards', Card), 'cards': ('checklists', Checklist)}
        var_name = '_' + self.__class__.__name__ + '__' + switch[self.__prefix][0]
        get_children_jsons = getattr(self, 'set_' + switch[self.__prefix][0])
        class_ref = switch[self.__prefix][1]

        get_children_jsons()
        for json in self.__dict__[var_name]:
            new_Object = class_ref(json['id'])
            new_Object.__json = json
            self.children.append(new_Object) 
    
    def setup(self):
        """Acquire this object's json, acquire it's direct children JSON and instantiate them."""
        self.get_self()
        self.populate()

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
    def set_cards(self):
        """Acquire Cards from a board or list in Trello."""
        response = self._request('GET', self.id, 'cards')
        self.__cards = response.json()
        return response

    def set_lists(self):
        """Acquire Lists from a board.."""
        response = self._request('GET', self.id, 'lists')
        self.__lists = response.json()
        return response
    
    def set_checklists(self):
        """Acquire Checklists from a board.."""
        response = self._request('GET', self.id, 'checklists')
        self.__checklists = response.json()
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


os.environ['trello_key'] = '637c56e248984ec499c0361ccb63f695'
os.environ['trello_token'] = '44162f9fa00913303974d79d1151c3414ee0d9978f2e6720ebff65adf5afe3bf'

brd = Board('62221524f3b7441300da7a88')

# brd.get_self()
# brd.populate()
brd.setup()

print(brd['name'], brd['id'])

for obj in brd.extract(brd.lists, 'id', 'name', 'idBoard'):
    print(obj)

for obj in brd.lists:
    print(obj['id'], obj['name'])

for obj in brd.search(brd.lists, 'name', 'PEDIDOS', 'id', 'name'):
    print(obj)

# for lst in brd.children:
#     lst: List
#     print(lst.to_tuple('name', 'id'))
#