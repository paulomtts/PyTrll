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

        self.__boards = ModifiedList()

        if threads != None:
            self.__threads = threads

        if chunk_size != None:
            self.__chunk_size = chunk_size

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(pools={self.__request_pool!r}, chunk_size={self.__chunk_size!r})'

    def __getitem__(self, *tup: tuple):
        brd: Board
        args = tup[0]

        if isinstance(args, slice):
            key = args.start
            val = args.stop

            for brd in self.__boards:
                if brd[key] == val:
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
                'get_custom_fields':      'boards/{id}/customFields',

                'create_list':            'boards/{id}/lists',
            },

            'List':{
                'get_cards':              'lists/{id}/cards',

                'create_card':            'cards',
                'delete_card':            'cards/{id}',
            },

            'Card':{
                'get_checklists':         'cards/{id}/checklists',
                'get_attachments':        'cards/{id}/attachments',
                'get_custom_field_items': 'cards/{id}/customFieldItems',

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
                'update_self':            'cards/{id}/checkItem/{idCheckItem}',
            },
            
            'CustomFieldItem':{
                'update_self':            'cards/{idCard}/customField/{idCustomField}/item',
            },
        }

        body = switch[class_name][function_name].format(**kwargs)
        return f'https://api.trello.com/1/{body}'
    
    # SCRIPT METHODS #######################################################
    def set_family(self, obj):
        """Fully setup  self and all objects belonging to the layer hierarchically below this object.
        Example: when called from a Board object, this method will setup self and all lists belonging to
        that board."""

        if f'{obj.id}__family__' in self.request_pool.keys():
            raise ValueError(f'\'{obj.id}__family__\' is a reserved keyword. Please remove it from the queue before executing this method.')

        fnc_sw = {'boards':     obj.get_lists, 
                  'lists':      obj.get_cards, 
                  'cards':      obj.get_checklists,}
                #   'checklists': self.get_checkitems}

        self.queue(f'{obj.id}__family__', obj.get_self)
        self.queue(f'{obj.id}__family__', fnc_sw[obj.trello_class])
        
        self.execute(f'{obj.id}__family__')
            
        obj_sw = {'boards':     obj.lists, 
                  'lists':      obj.cards, 
                  'cards':      obj.checklists,}
                #   'checklists': self.checkitems}

        for obj in obj_sw[obj.trello_class]:
            self.queue(f'{obj.id}__family__', obj.get_self)
        
        self.execute(f'{obj.id}__family__')

    # METHODS ##############################################################   
    def request(self, method: str, params: dict = None, payload: dict = None, cls: str = '', wildcard: str = '', **kwargs: dict):
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
        
        if payload:
            payload.update(self.query)
        else:
            payload = {}

        url = self._build_url(class_name, function_name, wildcard=wildcard, **kwargs)
        response = rq.request(method, url, headers=self.headers, params=params, json=payload)

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

        if self.__request_pool.get(key, None) is None:
            return

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
        response = self.request('GET')

        if response.status_code == 200:
            self.__boards = ModifiedList([Board(self, json) for json in response.json()])

        return response

    def create_board(self, name: str):
        """Create a board in this Trello user."""
        params = {'name': name}.update(self.query)

        response = self.request('POST', params=params)

        if response.status_code == 200:
            self.__boards.append(Board(self, response.json()))

        return response
    
    def delete_board(self, board_id: str):
        """Delete a board in this Trello user."""
        response = self.request('DELETE', id=board_id)

        if response.status_code == 200:
            for idx, brd in enumerate(self.__boards):
                if brd.id == board_id:
                    self.__boards.pop(idx)
                    break

        return response       


class BaseObject(ABC):
    """A generic blueprint for Trello objects."""
    
    @abstractmethod
    def __init__(self, app: App, js: dict, trello_class: str):
        self.__app          :App       = app
        self.__trello_class :str       = trello_class

        self.__json         :json      = js
        self.__id           :str       = js['id']

    def __getitem__(self, *tup: str):
        """Contains search mechanisms."""
        args = tup[0]

        if isinstance(args, str):
            return self.json[args]
        elif isinstance(args, tuple):
            if all(isinstance(arg, str) for arg in args):
                return [self.json[arg] for arg in args]
        elif isinstance(args, ModifiedList):
            return [arg.json for arg in args]
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

    @property
    def trello_class(self):
        return self.__trello_class

    # METHODS ##############################################################   
    def dump(self, js = None):
        """Pretty print a json."""
        
        if js == None:
            js = self.json
        
        if not isinstance(js, list):
            js = [js]

        for obj in js:
            print(json.dumps(obj, indent=4, sort_keys=False))

    def get_child_list(self):
        pass

    # REQUESTS #############################################################
    def get_self(self):
        """Acquire a JSON representing this object from Trello. \nURL: varies according to calling object."""
        response = self.app.request('GET', cls='BaseObject', wildcard=self.__trello_class, id=self.id)
        
        if response.status_code == 200:
            self.__json = response.json()
            
        return response

    def update_self(self, params: dict=None):
        """Update an object in Trello. \nURL: varies according to calling object."""
        response = self.app.request('PUT', params=params, cls='BaseObject', wildcard=self.__trello_class, id=self.id)
        
        if response.status_code == 200:
            self.__json = response.json()
        
        return response


class Board(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'boards')
        self.__lists = ModifiedList()
        self.__cards = ModifiedList()
        self.__checklists = ModifiedList()
        self.__custom_fields = ModifiedList()

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

    @property
    def custom_fields(self):
        return self.__custom_fields
    
    # REQUESTS #############################################################
    def get_lists(self):
        """Acquire Lists from a board. \nURL: /1/boards/{id}/lists"""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__lists = ModifiedList([List(self.app, json) for json in response.json()])
        
        return response
    
    def get_cards(self):
        """Acquire Cards from a board or list in Trello. \nURL: /1/boards/{id}/cards"""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__cards = ModifiedList([Card(self.app, json) for json in response.json()])
        
        return response

    def get_checklists(self):
        """Acquire Checklists from a board. \nURL: /1/boards/{id}/checklists"""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checklists = ModifiedList([Checklist(self.app, json) for json in response.json()])
        
        return response

    def get_custom_fields(self):
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__custom_fields = ModifiedList([CustomField(self.app, json) for json in response.json()])
        
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
        self.__cards = ModifiedList()

    # PROPERTIES ###########################################################    
    @property
    def cards(self):
        return self.__cards

    # REQUESTS #############################################################
    def get_cards(self):
        """Get all lists in a board."""
        response = self.app.request('GET', id=self.id)

        if response.status_code == 200:
            self.__cards = ModifiedList([Card(self.app, json) for json in response.json()])

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
        response = self.app.request('DELETE', id=card_id)
        
        if response.status_code == 200:
            for idx, crd in enumerate(self.__cards):
                if crd.id == card_id:
                    self.__cards.pop(idx)
                    break

        return response


class Card(BaseObject):
    def __init__(self, app: App, json: dict):
        super().__init__(app, json, 'cards')
        self.__checklists = ModifiedList()
        self.__attachments = ModifiedList()
        self.__custom_field_items = ModifiedList()

    # PROPERTIES ###########################################################
    @property
    def checklists(self):
        return self.__checklists

    @property
    def attachments(self):
        return self.__attachments
    
    @property
    def custom_field_items(self):
        return self.__custom_field_items

    # METHODS ##############################################################
    def build_custom_field_items(self, board: Board):
        """Create empty custom field objects in a card."""
        
        self.__custom_field_items = ModifiedList([CustomFieldItem(self.app, {
            'id': '', 
            'idCustomField': cf.json['id'],
        }, cf.json['name'], self.id) for cf in board.custom_fields])

    # REQUESTS #############################################################
    def get_checklists(self):
        """Get all checklists in a card."""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checklists = ModifiedList([Checklist(self.app, json) for json in response.json()])

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

    def get_attachments(self):
        """Get all attachments in a card."""
        response = self.app.request('GET', id=self.id)
    
        if response.status_code == 200:
            self.__attachments = ModifiedList([Attachment(self.app, json) for json in response.json()])

        return response     

    def create_attachment(self, name: str, url: str = '', file: str = '', 
                          mime_type: str = '', set_cover: bool = 'false'):
        """Create an attachment in a card.
        
        - file: in binary format."""
        
        params = {'name': name,
                  'url':  url,
                  'file': file,
                  'mimeType': mime_type,
                  'setCover': set_cover}
        
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
        self.__checkitems = ModifiedList()

    # PROPERTIES ###########################################################    
    @property
    def checkitems(self):
        return self.__checkitems

    # REQUESTS #############################################################
    def get_checkitems(self):
        """Get all checkitems in a checklist."""
        response = self.app.request('GET', id=self.id)
        
        if response.status_code == 200:
            self.__checkitems = ModifiedList([Checkitem(self.app, json) for json in response.json()])

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

        print(self.json)
        response = self.app.request('PUT', params=params, id=card_id, idCheckItem=self.id)
        
        if response.status_code == 200:
            self._BaseObject__json = response.json()
        
        return response


class CustomField(BaseObject):
    def __init__(self, app: App, js: dict):
        super().__init__(app, js, 'customFields')


class CustomFieldItem(BaseObject):
    def __init__(self, app: App, js: dict, name: str, card_id: str):
        super().__init__(app, js, 'customFieldItems')

        self.__kind         :str       = None
        self.__value        :str       = None
        self.__name         :str       = name
        self.__card_id      :str       = card_id
    
    # PROPERTIES ###########################################################    
    @property
    def kind(self):
        return self.__kind

    @property
    def value(self):
        return self.__value

    @property
    def name(self):
        return self.__name

    @property
    def card_id(self):
        return self.__card_id

    # REQUESTS #############################################################
    def update_self(self, text: str ='', number: str ='', date: str='', checked: str ='', params: dict = None):
        """Update a custom field in Trello. Each field can only hold a single value,
        therefore passing multiple value arguments will result in an API Error."""
        
        payload = {
            'value':{
                'text': text,
                'number': number,
                'date': date,
                'checked': checked,
            }
        }
        
        payload = {'value': {key:val for key, val in payload['value'].items() if val != ''}}

        response = self.app.request('PUT', params=params, payload=payload, idCard=self.card_id, idCustomField=self.json['idCustomField'])
        
        if response.status_code == 200:
            self._BaseObject__json = response.json()
            self.__kind = list(payload['value'].keys())[0]
            self.__value = list(payload['value'].values())[0]
        
        return response


class Attachment(BaseObject):
    def __init__(self, app: App, js: dict):
        super().__init__(app, js, 'attachments')


class ModifiedList(list):
    """A custom list for the Trello objects. Facilitates __getitem__ syntax in
    other classes."""

    types = [Board, List, Card, Checklist, Checkitem, CustomField, CustomFieldItem, Attachment]
    
    def __init__(self, data: list = None) -> None:
        if data is None:
            data = []
        elif not all(type(obj) in self.types for obj in data):
            raise TypeError(f'Can only accept objects of the following types: {self.types!r}')
        
        list.__init__(self, data)
        for idx, val in enumerate(data):
            super(ModifiedList, self).__setitem__(idx, val)

    def __getitem__(self, entry):
        if isinstance(entry, int):
            return super(ModifiedList, self).__getitem__(entry)
        
        elif isinstance(entry, str):
            return tuple(obj.json[entry] for obj in self)

        elif isinstance(entry, slice):
            key = entry.start
            val = entry.stop

            if isinstance(key, int) and isinstance(val, int):
                super.__getitem__((key, val),)


            if not hasattr(val, '__iter__') or type(val) is str:
                val = [val]
            
            result = [obj for obj in self if obj[key] in val]

            if len(result) == 1: 
                result = result[0]
        
            return result

        elif isinstance(entry, dict):
            results = []

            for obj in self:
                appnd = True

                for key, values in entry.items():
                    if isinstance(values, str):
                        values = [values]
                    if not isinstance(values, list):
                        raise TypeError('Keys must be associated with lists.')

                    if obj.json[key] not in values:
                        appnd = False
                        break
                
                if appnd:
                    results.append(obj)
                    
            if len(results) == 1:
                return results[0]
            return results
        
        elif isinstance(entry, tuple):
            
            if all(isinstance(obj, str) for obj in entry):
                return [tuple(obj.json[item] for item in entry) for obj in self]
            
            elif all(isinstance(obj, slice) for obj in entry):
                
                to_iterable = lambda val: val if hasattr(val, '__iter__') else [val]
                get_object = lambda pair: pair[0] if pair[0][pair[1]] in to_iterable(pair[2]) else None
                split_lst = lambda lst, chunk_size: (lst[i:(i+chunk_size)] for i in range(0, len(lst), chunk_size))

                tup_iterator = ((obj, slc.start, slc.stop) for obj in self for slc in entry)
                result = list(map(get_object, tup_iterator))

                result = split_lst(result, len(entry))
                result = (res for res in result if None not in res)

                flat_result = []
                for group in result:
                    for res in group:
                        if res not in flat_result:
                            flat_result.append(res)

                if len(flat_result) == 1:
                    return flat_result[0]
                return flat_result

            elif isinstance(entry[0], dict) and all(isinstance(obj, str) for obj in entry[1:]):
                
                results = []

                for obj in self:
                    appnd = True

                    for key, values in entry[0].items():
                        if isinstance(values, str):
                            values = [values]
                        if not isinstance(values, list):
                            raise TypeError('Keys must be associated with lists.')

                        if obj.json[key] not in values:
                            appnd = False
                            break
                        
                    if appnd:
                        results.append(obj.json)

                results = [{key:val for key, val in js.items() if key in entry[1:]} for js in results]

                if len(results) == 1:
                    if len(entry[1:]) == 1:
                        return results[0][entry[-1]]
                    return results[0]
                return [{key:val for key, val in js.items() if key in entry[1:]} for js in results]

            else:
                raise TypeError("Incorrect mix of types. Provide a dictionary followed by strings.")

