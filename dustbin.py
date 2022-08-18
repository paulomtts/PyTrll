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