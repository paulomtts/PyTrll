
Trello API: https://developer.atlassian.com/cloud/trello/rest/
Main Developer: Paulo Mattos

# GOAL
The goal of this module is NOT to precisely reflect Trello's API, but rather to provide a
simple set of tools with which to allow python users to easily read and manipulate Trello.

# METHOD RATIONALE
PROPERTIES:       single-purpose | private | properties of an object
PRIVATE:          single-purpose | private | only accessible to itself or its heirs
METHODS:          single-purpose | public  | general tasks
SCRIPT METHODS:   multi-purpose  | public  | provided for convenience
REQUESTS:         single-purpose | public  | perform requests on the Trello API

# OBJECT PROPERTIES 
All objects possess the following properties:
- json:       a JSON acquired from the Trello API corresponding to this object's id property.
- id:         an identification string from Trello, this is provided for conveniency

There are no setter properties for any objects. Any setting of variables must be done through 
the appropriate request, thus ensuring that any data in a property in all likelihood originated 
from Trello. Python does not enforce property privacy, therefore we cannot truly prevent a 
developer from meddling with this system.


## Object setup
```
brd = Board('id_number_here')
```

## Printing jsons 
```
print(brd.json)
brd.dump(brd.json)
```


## Sequential requests 
```
brd.get_self()
brd.get_lists()

for lst in brd.lists:
    lst.get_self()
```

## Multithreading requests
```
for fn in [brd.get_self, brd.get_lists]:
    brd.app.queue(fn)
print(brd.app.execute())

for lst in brd.lists:
    brd.app.queue(lst.get_self)
print(brd.app.execute())

brd.app.queue(brd.lists[0].update_self, ({'name': 'NEW NAME'}))
```

## Acessing properties
```
# [str] -> str
brd['name']

# [str, ...] -> json{str: val, str: val, ...}
brd['name', 'id']

# [list] -> list[json, ...]
brd[brd.lists]

# [list, str, ...] -> list[json, ...]
brd[brd.lists, 'name', 'id'] 

# [list, (str, str)]   |   [list, (str, [str, ...])] -> list[json, ...]
brd[brd.lists, {'name': ['PEDIDOS', 'dev_list']}]

# [list, (str, str), str, ...]   |   [list, (str, [str, ...]), str, ...] -> list[json, ...]
brd[brd.lists, {'name': ['PEDIDOS', 'dev_list']}, 'name', 'id']
```