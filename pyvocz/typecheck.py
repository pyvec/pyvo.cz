# See the typecheck function for documentation.
#
# This was written on a train, with bad internet connection: I wasn't able to
# find a library that does this already; if one exists it should be used
# instead.
#
# This differs from typechecking tools like "mypy" in that it checks *data*,
# not code. It also checks at one point in time -- after an object is created;
# indeed, pyvocz won't validate with mypy, because *while* the data structure
# is being created, some non-Optional fields are temporarily set to None.
#
# The code is not generic; it can be extended if more kinds of annotations are
# added to the data model.

import typing
import contextlib

def typecheck(obj):
    """Check that the given object corresponds to type hints

    Types are checked using class member annotations of obj's class.
    All of the instance's attributes must be typed, and types are checked
    recursively.
    """
    _TypeChecker().validate_hinted_attrs(obj)


class _TypeChecker:
    """Internal class for holding state"""
    path = ''

    def __init__(self):

        # Path to object currently being handled
        # The concatenation of path's elements will describe the object
        self.path = []

        # Set of object IDs that were already checked
        self.memo = set()

    @contextlib.contextmanager
    def recurse(self, path_elem):
        """Context for handling an object"""
        self.path.append(path_elem)
        #print(f'Validating {"".join(self.path)}')
        yield
        self.path.pop()

    def validate_hinted_attrs(self, obj):
        """Validate all attributes of the given object"""
        tp = type(obj)
        if id(obj) in self.memo:
            return
        self.memo.add(id(obj))
        type_hints = typing.get_type_hints(tp)
        for attr_name, attr_type in type_hints.items():
            value = getattr(obj, attr_name)
            with self.recurse(f'.{attr_name}'):
                self.validate_type(value, attr_type)
        obj_dict = getattr(obj, '__dict__', None)
        if obj_dict is not None:
            extra_attrs = obj_dict.keys() - type_hints.keys()
            if extra_attrs:
                raise ValueError(
                    f'{"".join(self.path)}: object has untyped attributes: ' +
                    f'{extra_attrs}'
                )

    def validate_type(self, value, expected_type):
        """Validate that `value` corresponds to the given type annotation"""
        origin = getattr(expected_type, '__origin__', None)
        if expected_type == typing.Any:
            pass
        elif origin in (dict, typing.Dict):
            self.validate_type(value, dict)
            key_type, val_type = expected_type.__args__
            for key, val in value.items():
                with self.recurse(f' key {key!r}'):
                    self.validate_type(key, key_type)
                with self.recurse(f'[{key!r}]'):
                    self.validate_type(val, val_type)
        elif origin in (list, typing.List):
            self.validate_type(value, list)
            [item_type] = expected_type.__args__
            for i, item in enumerate(value):
                with self.recurse(f'[{i}]'):
                    self.validate_type(item, item_type)
        elif origin == typing.Union:
            exception_to_raise = None
            for option in expected_type.__args__:
                try:
                    self.validate_type(value, option)
                except TypeError as e:
                    if exception_to_raise is None:
                        exception_to_raise = e
                else:
                    return
            else:
                raise exception_to_raise
        else:
            if not isinstance(value, expected_type):
                raise TypeError(
                    f'{"".join(self.path)}: {value} is not a {expected_type}'
                )
            if not isinstance(value, (int, str)):
                self.validate_hinted_attrs(value)
