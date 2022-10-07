from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from inspect import stack

import requests as rq
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
        self.__headers          :dict       = {"Accept": "application/json"}
        self.__query            :dict       = {'key'     : key,
                                               'token'   : token}
        self.__request_pool     :dict       = {}
        self.__threads          :int        = os.cpu_count() + 4
        self.__chunk_size       :int        = chunk_size
        self.__api_interval     :float      = api_interval

        self.__boards = CustomList()

        if threads != None:
            self.__threads = threads

        if chunk_size != None:
            self.__chunk_size = chunk_size

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(pools={self.__request_pool!r}, chunk_size={self.__chunk_size!r})'

    def __getitem__(self, *tup: tuple):
        brd: Board
        
        args = tup[0]

        if isinstance(args, str):
            for brd in self.__boards:
                if brd['name'] == args:
                    return brd

    # PROPERTIES ###########################################################
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
    
    @property
    def boards(self):
        return self.__boards

    # PRIVATE ##############################################################
    def _build_url(self, class_name: str, function_name: str, **kwargs: dict) -> str:
        """Build URLs for requests."""

        switch = {
            'App':{
                'get_boards':             'members/me/boards/all',
                
                'create_board':           'boards',
                'delete_board':           'boards/{id}',
            },

            'BaseObject':{
                'get_self':               '{wildcard}/{id}',
                'update_self':            '{wildcard}/{id}',
            },

            'Board':{
                'get_lists':              'boards/{id}/lists',
                'get_cards':              'boards/{id}/cards',
                'get_checklists':         'boards/{id}/checklists',

                'create_list':            'boards/{id}/lists',
            },

            'List':{
                'get_cards':              'lists/{id}/cards',

                'create_card':            'cards',
                'delete_card':            'cards/{id}',
            },

            'Card':{
                'get_checklists':         'cards/{id}/checklists',

                'create_checklist':       'cards/{id}/checklists',
                'delete_checklist':       'cards/{id}/checklists/{idChecklist}',

                'create_attachment':      'cards/{id}/attachments',
                'delete_attachment':      'cards/{id}/attachments/{idAttachment}',
            },

            'Checklist':{
                'get_checkitems':         'checklists/{id}/checkitems',

                'create_checkitem':       'checklists/{id}/checkitems',
                'delete_checkitem':       'checklists/{id}/checkItems/{idCheckItem}',
            },

            'Checkitem':{
                'get_self':               'checklists/{id}/checkItems/{idCheckItem}',
                'update_self':            'cards/{id}/checkItem/{idCheckItem}'
            }
        }

        body = switch[class_name][function_name].format(**kwargs)
        return f'https://api.trello.com/1/{body}'
        
    # METHODS ##############################################################   
    def request(self, method: str, params: dict = None, cls: str = '', wildcard: str = '', **kwargs: dict):
        """Perform a request.
        
        - method: request type.
        - params: parameter dictionary containing request-specific details.
        - cls & wildcard: meant for requests performed from methods in the BaseObject class.
        - keyword args: ids to be filled in the URL."""
        
        if not cls:
            class_name = stack()[1][0].f_locals['self'].__class__.__name__
        else:
            class_name = cls
        
        function_name = stack()[1].function

        if params:
            params.update(self.query)
        else:
            params = self.query

        url = self._build_url(class_name, function_name, wildcard=wildcard, **kwargs)

        response = rq.request(method, url, headers=self.headers, params=params)

        if response.status_code != 200:
            raise APIError(response)
        return response

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

    # REQUESTS #############################################################
    def get_boards(self):
        """Populate the list of boards for this Trello user."""
        response = rq.request('GET', 'https://api.trello.com/1/members/me/boards/all', 
                              headers=self.headers,
                              params=self.query)

        if response.status_code == 200:
            self.__boards = CustomList([Board(self, json) for json in response.json()])

        return response

    def create_board(self, name: str):
        """Create a board in this Trello user."""
        params = {'name': name}.update(self.query)

        response = rq.request('POST', 'https://api.trello.com/1/boards', 
                              headers=self.headers,
                              params=params)

        if response.status_code == 200:
            self.__boards.append(Board(self, response.json()))

        return response
    
    def delete_board(self, board_id: str):
        """Delete a board in this Trello user."""
        response = rq.request('DELETE', f'https://api.trello.com/1/boards/{board_id}', 
                              headers=self.headers,
                              params=self.query)

        if response.status_code == 200:
            for idx, brd in enumerate(self.__boards):
                if brd.id == board_id:
                    self.__boards.pop(idx)
                    break

        return response       


class BaseObject(ABC):
    """A generic blueprint for Trello objects."""
    
    @abstractmethod
    def __init__(self, app: App, js: dict, prefix: str):
        self.__app          :App       = app
        self.__prefix       :str       = prefix

        self.__json         :json      = js
        self.__id           :str       = js['id']

    def __getitem__(self, *tup: str):
        """Contains search mechanisms."""
        args = tup[0]

        if isinstance(args, str):
            return self.json[args]
        elif isinstance(args, CustomList):
            return [arg.json for arg in args]
        elif isinstance(args, tuple):
            if all(isinstance(arg, str) for arg in args):
                return [self.json[arg] for arg in args]
        raise TypeError(f'Invalid {type(args)} argument.')

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.__json["name"]!r}, {self.__id!r})'

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

        if f'{self.id}__family__' in self.app.request_pool.keys():
            raise ValueError(f'\'{self.id}__family__\' is a reserved keyword. Please remove it from the queue before executing this method.')

        fnc_sw = {'boards':     self.get_lists, 
                  'lists':      self.get_cards, 
                  'cards':      self.get_checklists,}
                #   'checklists': self.get_checkitems}

        self.app.queue(f'{self.id}__family__', self.get_self)
        self.app.queue(f'{self.id}__family__', fnc_sw[self.__prefix])
        self.app.execute(f'{self.id}__family__')
            
        obj_sw = {'boards':     self.lists, 
                  'lists':      self.cards, 
                  'cards':      self.checklists,}
                #   'checklists': self.checkitems}

        for obj in obj_sw[self.__prefix]:
            self.app.queue(f'{self.id}__family__', obj.get_self)
        self.app.execute(f'{self.id}__family__')

    # REQUESTS #############################################################
    def get_self(self):
        """Acquire a JSON representing this object from Trello. \nURL: varies according to calling object."""
        response = self.app.request('GET', cls='BaseObject', wildcard=self.__prefix, id=self.id)
        
        if response.status_code == 200:
            self.__json = response.json()
            
        return response

    def update_self(self, params: dict=None):
        """Update an object in Trello. \nURL: varies according to calling object."""
        response = self.app.request('PUT', params=params, cls='BaseObject', wildcard=self.__prefix, id=self.id)
        
        if response.status_code == 200:
            self.__json = response.json()
        
        return response


class Board(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'boards')
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
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__lists = CustomList([List(self.app, json) for json in response.json()])
        
        return response
    
    def get_cards(self):
        """Acquire Cards from a board or list in Trello. \nURL: /1/boards/{id}/cards"""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__cards = CustomList([Card(self.app, json) for json in response.json()])
        
        return response

    def get_checklists(self):
        """Acquire Checklists from a board. \nURL: /1/boards/{id}/checklists"""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checklists = CustomList([Checklist(self.app, json) for json in response.json()])
        
        return response

    def create_list(self, name: str, pos: str = 'bottom'):
        """Create a list in a board.\nURL: /1/boards/{id}/lists"""
        params = {'name':    name,
                  'pos':     pos}

        response = self.app.request('POST', params=params, id=self.id)

        if response.status_code == 200:
            self.__lists.append(List(self.app, response.json()))

        return response

class List(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'lists')
        self.__cards = CustomList()

    # PROPERTIES ###########################################################    
    @property
    def cards(self):
        return self.__cards

    # REQUESTS #############################################################
    def get_cards(self):
        """Get all lists in a board."""
        response = self.app.request('GET', id=self.id)

        if response.status_code == 200:
            self.__cards = CustomList([Card(self.app, json) for json in response.json()])

        return response

    def create_card(self, title: str = '', description: str = '', start_date: str = '', due_date: str = '', pos: str = 'bottom'):
        """Create a card in a list."""
        params = {'idList':  self.id,
                  'name':    title,
                  'desc':    description,
                  'start':   start_date,
                  'due':     due_date,
                  'pos':     pos}

        response = self.app.request('POST', params=params)

        if response.status_code == 200:
            self.__cards.append(Card(self.app, response.json()))

        return response

    def delete_card(self, card_id: str):
        """Delete a card."""
        response = self.app.request('DELETE', id=self.id)
        
        if response.status_code == 200:
            for idx, crd in enumerate(self.__cards):
                if crd.id == card_id:
                    self.__cards.pop(idx)
                    break

        return response


class Card(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'cards')
        self.__checklists = CustomList()
        self.__attachments = CustomList()

    # PROPERTIES ###########################################################
    @property
    def checklists(self):
        return self.__checklists

    @property
    def attachments(self):
        return self.__attachments

    # REQUESTS #############################################################
    def get_checklists(self):
        """Get all checklists in a card."""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checklists = CustomList([Checklist(self.app, json) for json in response.json()])

        return response

    def create_checklist(self, title: str, pos: str = 'bottom'):
        """Add a checklist to a card."""
        params = {'idCard':  self.id,
                  'name':    title,
                  'pos':     pos}
                 
        response = self.app.request('POST', params=params, id=self.id)

        if response.status_code == 200:
            self.__checklists.append(Checklist(self.app, response.json()))

        return response

    def delete_checklist(self, clist_id: str):
        """Delete a checklist from a card."""
        response = self.app.request('DELETE', id=self.id, idChecklists=clist_id)
        
        if response.status_code == 200:
            for idx, clist in enumerate(self.__checklists):
                if clist.id == clist_id:
                    self.__checklists.pop(idx)
                    break

        return response

    def create_attachment(self, name: str, url: str):
        """Create an attachment in a card."""
        
        #############
        # Needs to be reworked to include other arguments of the endpoint
        #############

        params = {'name': name,
                  'url':  url}
        
        response = self.app.request('POST', params=params, id=self.id)

        if response.status_code == 200:
            self.__attachments.append(Attachment(self.app, response.json()))
        
        return response

    def delete_attachment(self, attach_id: str):
        """Delete an attachment in a card."""
        response = self.app.request('DELETE', id=self.id, idAttachment=attach_id)

        if response.status_code == 200:
            for idx, attach in enumerate(self.__attachments):
                if attach.id == attach_id:
                    self.__attachments.pop(idx)
                    break
        
        return response



class Checklist(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'checklists')
        self.__checkitems = CustomList()

    # PROPERTIES ###########################################################    
    @property
    def checkitems(self):
        return self.__checkitems

    # REQUESTS #############################################################
    def get_checkitems(self):
        """Get all checkitems in a checklist."""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checkitems = CustomList([Checkitem(self.app, json) for json in response.json()])

        return response

    def create_checkitem(self, title: str, pos: str = 'bottom', checked: str = 'false'):
        """Add a checkitem to a checklist."""
        params = {'name':    title,
                  'pos':     pos,
                  'checked': checked}
                
        response = self.app.request('POST', params=params, id=self.id)

        if response.status_code == 200:
            self.__checkitems.append(Checkitem(self.app, response.json()))

        return response

    def delete_checkitem(self, citem_id: str):
        """Delete a checkitem from a list."""
        response = self.app.request('DELETE', id=self.id, idCheckItem=citem_id)
        
        if response.status_code == 200:
            for idx, citem in enumerate(self.__checkitems):
                if citem.id == citem_id:
                    self.__checkitems.pop(idx)
                    break

        return response


class Checkitem(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'checkitems')

    # REQUESTS #############################################################
    def get_self(self):
        """Acquire a JSON representing this object from Trello."""
        
        clist_id = self.json['idChecklist']
        response = self.app.request('GET', id=clist_id, idCheckItem=self.id)
        
        if response.status_code == 200:
            self._BaseObject__json = response.json()
            
        return response

    def update_self(self, card_id: str, params: dict = None):
        """Update checkitem in Trello."""

        response = self.app.request('PUT', params=params, id=card_id, idCheckItem=self.id)
        
        if response.status_code == 200:
            self._BaseObject__json = response.json()
        
        return response
    
    def set_family(self):
        pass


class CustomField(BaseObject):
    def __init__(self, app: App, js: dict):
        super().__init__(app, js, 'customFields')

        self.__value = None
    
    # PROPERTIES ###########################################################    
    @property
    def value(self):
        return self.__value

    # REQUESTS #############################################################
    def set_family(self):
        pass


class Attachment(BaseObject):
    def __init__(self, app: App, js: dict):
        super().__init__(app, js, 'attachments')


class CustomList(list):
    """A custom list for the Trello objects. Facilitates __getitem__ syntax in
    other classes."""

    types = [Board, List, Card, Checklist]
    
    def __init__(self, data: list = None) -> None:
        if data is None:
            data = []
        elif not all(type(obj) in self.types for obj in data):
            raise TypeError(f'Can only accept objects of the following types: {self.types!r}')
        
        list.__init__(self, data)
        for idx, val in enumerate(data):
            super(CustomList, self).__setitem__(idx, val)

    def __getitem__(self, entry):
        if isinstance(entry, int):
            return super(CustomList, self).__getitem__(entry)
        
        elif isinstance(entry, slice):
            return super(CustomList, self).__getitem__(entry)

        elif isinstance(entry, str):
            return tuple(obj.json[entry] for obj in self)
        
        elif isinstance(entry, dict):
            results = []

            for obj in self:
                appnd = True

                for key, values in entry.items():
                    if not isinstance(values, list):
                        raise TypeError('Keys must be associated with lists.')

                    if obj.json[key] not in values:
                        appnd = False
                        break
                
                if appnd:
                    results.append(obj.json)

            return results
        
        elif isinstance(entry, tuple):
            
            if all(isinstance(obj, str) for obj in entry):
                return [tuple(obj.json[item] for item in entry) for obj in self]
            
            elif isinstance(entry[0], dict) and all(isinstance(obj, str) for obj in entry[1:]):
                
                results = []

                for obj in self:
                    appnd = True

                    for key, values in entry[0].items():
                        if not isinstance(values, list):
                            raise TypeError('Keys must be associated with lists.')

                        if obj.json[key] not in values:
                            appnd = False
                            break
                        
                    if appnd:
                        results.append(obj.json)

                return [{key:val for key, val in obj.items() if key in entry[1:]} for obj in results]
            else:
                raise TypeError("Incorrect mix of types. Provide a dictionary followed by strings.")


key = '637c56e248984ec499c0361ccb63f695'
token = '44162f9fa00913303974d79d1151c3414ee0d9978f2e6720ebff65adf5afe3bf'
brd_id = '62221524f3b7441300da7a88'
brd_name = 'Agendas (Novo)'


start = time.perf_counter()

app = App(key, token, api_interval=0.0)
app.get_boards()

brd = app['Agendas (Novo)']
brd.set_family()
brd.get_cards()

# for i in range(1, 10):
#     app.queue('cards', brd.lists[0].create_card, f'Card {i}', start_date='2022-01-01', due_date='2022-12-31', pos=f'{i}')
# app.execute('cards')
# print(0)

# for crd in brd.lists[0].cards:
#     app.queue('checklists', crd.create_checklist, crd['name'])
# app.execute('checklists')
# print(1)

# checkitem_lst = ['abc', 'def']
# for crd in brd.lists[0].cards:
#     for clst in crd.checklists:
#         for txt in checkitem_lst:
#             app.queue('checkitems', clst.create_checkitem, txt, 'bottom')
# app.execute('checkitems')
# print(2)

# citem: Checkitem
# for crd in brd.lists[0].cards:
#     for clst in crd.checklists:
#         for citem in clst.checkitems:
#             # citem.dump()
#             app.queue('tick', citem.update_self, crd.id, params={'state': 'complete'})
# app.execute('tick')
# print(3)


# print(brd['name', 'id'])
# print(brd[brd.lists])

# print(brd.lists['name'])
# print(brd.lists['name', 'id'])
# print(brd.lists[{'name': ['PEDIDOS', 'ITENS EM ANDAMENTO']}])
# print(brd.lists[{'name': ['PEDIDOS', 'ITENS EM ANDAMENTO']}, 'name'])
# print(brd.lists[{'name': ['PEDIDOS', 'ITENS EM ANDAMENTO']}, 'name', 'id'])

end = time.perf_counter()
print(f'{end-start:.4f} seconds')