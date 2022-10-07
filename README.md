
Trello API: https://developer.atlassian.com/cloud/trello/rest/
Main Developer: Paulo Mattos

### NEXT UPDATES
- [ ] Add the Checkitem class
- [ ] Create various requests for all existing classes
- [x] Bracket-syntax rework

## GOAL
The goal of this module is NOT to precisely reflect Trello's API, but rather to provide a
simple set of tools with which to allow python users to easily read and manipulate Trello.

## METHOD RATIONALE
* PROPERTIES:       single-purpose | private | properties of an object
* PRIVATE:          single-purpose | private | only accessible to itself or its heirs
* METHODS:          single-purpose | public  | general tasks
* SCRIPT METHODS:   multi-purpose  | public  | provided for convenience
* REQUESTS:         single-purpose | public  | perform requests on the Trello API

## OBJECT PROPERTIES 
All objects possess the following properties:
- json:       a JSON acquired from the Trello API corresponding to this object's id property.
- id:         an identification string from Trello, this is provided for conveniency

There are no setter properties for any objects. Any setting of variables must be done through 
the appropriate request, thus ensuring that any data in a property in all likelihood originated 
from Trello. Python does not enforce property privacy, therefore we cannot truly prevent a 
developer from meddling with this system.


# USAGE EXAMPLES

## Object setup
```
key = '000'
token = 'AAA'
brd_id = '111'

app = App(key, token)
brd = Board(app, brd_id)
```

## Printing jsons 
```
print(brd.json)
brd.dump()
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
    app.queue(fn)
app.execute()

for lst in brd.lists:
    app.queue(lst.get_self)
app.execute()

app.queue(brd.lists[0].update_self, ({'name': 'sample_name0'}))
app.execute()
```

## Acessing properties
```
# [str] -> str
brd['name']

# [str, str, ...] -> json{str: val, str: val, ...}
brd['name', 'id']

# [list_like_attribute] -> list[json, ...]
brd[brd.lists]

# [str, ...] -> list[(val, val), (val, val), ...]
brd.lists['name', 'id'] 

# [{key: [val, val, ...]}] -> list[json, ...]
brd.lists[{'name': ['sample_name0', 'sample_name1']}]

# [{key: [val, val, ...]}, str, str] -> list[{key: val, ...}, ...]
brd.lists[{'name': ['sample_name0', 'sample_name1']}, 'name', 'id']
```