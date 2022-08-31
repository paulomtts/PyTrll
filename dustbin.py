# def populate(self):
#     """Populate this object with instances of it's children objects. i.e.: boards > lists"""
#     switch = {'boards': ('lists', List), 'lists': ('cards', Card), 'cards': ('checklists', Checklist)}
#     var_name = '_' + self.__class__.__name__ + '__' + switch[self.__prefix][0]
#     get_children_jsons = getattr(self, 'set_' + switch[self.__prefix][0])
#     class_ref = switch[self.__prefix][1]

#     get_children_jsons()
#     for json in self.__dict__[var_name]:
#         new_Object = class_ref(json['id'])
#         new_Object.__json = json
#         self.children.append(new_Object)

# def setup(self):
#     """Acquire this object's JSON and populate it's children objects. i.e.: boards > lists"""
    
#     self.set_self()

#     switch = {'boards': ('lists', List), 'lists': ('cards', Card), 'cards': ('checklists', Checklist)}
    
#     property_name = '_' + self.__class__.__name__ + '__' + switch[self.__prefix][0]
#     json_setter = getattr(self, 'get_' + switch[self.__prefix][0])
#     class_ref = switch[self.__prefix][1]

#     json_setter()
#     for json in self.__dict__[property_name]:
#         new_Object = class_ref(json['id'])
#         new_Object.__json = json
#         self.children.append(new_Object) 

# def to_tuple(self, *keys):
#     """Get specific data from this object's JSON and return it as a namedTuple."""
#     Object = namedtuple(self.__class__.__name__.lower(), [*keys])
#     return Object(*[self.json.get(key, None) for key in keys])


# def extract(look_in: list, *keys: str):
#     """Extract data from a list of JSONs and return it as a generator containing namedTuples."""
#     Object = namedtuple(extract.__name__, [*keys])
#     return ((Object(*[json.get(key, None) for key in keys]) for json in look_in))


# def search(look_in: list, look_by: str, look_for: str, *keys: str):
#     """Conditionally extract data from a list of JSONs and return it as a generator containing namedTuples."""
#     Object = namedtuple(search.__name__, [*keys])
#     return (Object(*[json.get(key, None) for key in keys]) for json in look_in if json[look_by] == look_for)

# def from_children(self, *keys: str):
#     """Extract data from the child objects."""
#     Object = namedtuple('extract', [*keys])
#     return ((Object(*child[keys]) for child in self.children))


# def __getitem__(self):
#         try:

#             print(tup)

#             # [str] -> str
#             if isinstance(arg, str):
#                 return self.json[arg]

#             # [list] -> list[json, ...]
#             elif isinstance(arg, list) and all(isinstance(key, (Board, List, Card)) for key in arg[1:]):
#                 return [obj.json for obj in arg]

#             # [str, ...] -> json{str: val, str: val, ...}
#             if isinstance(tup[0], tuple) and all(isinstance(key, str) for key in tup[0]):
#                 return json.dumps({key: self.json[key] for key in tup[0]})
            

#             # [list, (str, ...)] -> list[json, ...]
#             elif isinstance(tup[0][0], list) and all(isinstance(key, str) for key in tup[0][1]):
#                 json_lst= [
#                     {key:obj.json[key] for key in tup[0][1:]} 
#                     for obj in tup[0][0]
#                 ]

#                 return [json.dumps(js) for js in json_lst]

#             # [list, (str, str)]   |   [list, (str, [str, ...])] -> list[json, ...]
#             elif isinstance(tup[0], tuple) and isinstance(tup[0][1], tuple) and len(tup[0]) == 2:
#                 instance_lst   = tup[0][0]
#                 condition_key  = tup[0][1][0]
#                 value_lst      = tup[0][1][1]

#                 if not isinstance(value_lst, list): value_lst = [value_lst]
#                 return [instance.json for instance in instance_lst if instance.json[condition_key] in value_lst]

#             # [list, (str, str), str, ...]   |   [list, (str, [str, ...]), str, ...] -> list[json, ...]
#             elif isinstance(tup[0], tuple) and isinstance(tup[0][1], tuple) and all(isinstance(key, str) for key in tup[0][2:]):
#                 instance_lst   = tup[0][0]
#                 condition_key  = tup[0][1][0]
#                 value_lst      = tup[0][1][1]
#                 json_keys      = tup[0][2:]

#                 if not isinstance(value_lst, list): value_lst = [value_lst]
#                 json_lst = [
#                     {key:instance.json[key] for key in json_keys}
#                     for instance in instance_lst 
#                     if instance.json[condition_key] in value_lst
#                 ]

#                 return [json.dumps(js) for js in json_lst]

#         except KeyError as error:
#             raise KeyError(f"The {error} key could not be found in {self}'s JSON.") from None


    # def _add_child(self, json: dict):
    #     """Instantiate a child object, fill it with a JSON and add it to this object's children."""
    #     switch = {'Board': List, 'List':  Card, 'Card': Checklist}
    #     class_ = switch.get(self.__class__.__name__, None)
        
    #     child = class_(json['id'])
    #     child.__json = json
        
    #     self.children.append(child)


def fn(**a):
    print(a)

fn(a=0)