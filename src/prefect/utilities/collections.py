import collections
import json
from collections.abc import MutableMapping
from typing import Any, Generator, Iterable, Iterator, Union

DictLike = Union[dict, "DotDict"]


def flatten_seq(seq: Iterable) -> Generator:
    """
    Generator that returns a flattened list from a possibly nested list-of-lists
    (or any sequence type).

    Example:
        ```python
        flatten_seq([1, 2, [3, 4], 5, [6, [7]]])
        >>> [1, 2, 3, 4, 5, 6, 7]
        ```

    Args:
        - seq (Iterable): the sequence to flatten

    Returns:
        - generator: a generator that yields the flattened sequence
    """
    for item in seq:
        if isinstance(item, collections.Iterable) and not isinstance(
            item, (str, bytes)
        ):
            yield from flatten_seq(item)
        else:
            yield item


class DotDict(MutableMapping):
    """
    A `dict` that also supports attribute ("dot") access. Think of this as an extension
    to the standard python `dict` object.  **Note**: while any hashable object can be added to
    a `DotDict`, _only_ valid Python identifiers can be accessed with the dot syntax; this excludes
    strings which begin in numbers, special characters, or double underscores.

    Args:
        - init_dict (dict, optional): dictionary to initialize the `DotDict`
        with
        - **kwargs (optional): key, value pairs with which to initialize the
        `DotDict`

    Example:
        ```python
        dotdict = DotDict({'a': 34}, b=56, c=set())
        dotdict.a # 34
        dotdict['b'] # 56
        dotdict.c # set()
        ```
    """

    __protect_critical_keys__ = True

    def __init__(self, init_dict: DictLike = None, **kwargs: Any):
        if init_dict:
            self.update(init_dict)
        self.update(kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        """
        This method is defined for MyPy, which otherwise tries to type
        the inherited `.get()` method incorrectly.

        Args:
            - key (str): the key to retrieve
            - default (Any): a default value to return if the key is not found

        Returns:
            - Any: the value of the key, or the default value if the key is not found
        """
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.__dict__[key]  # __dict__ expects string keys

    def __setitem__(self, key: str, value: Any) -> None:
        # prevent overwriting any critical attributes
        if (
            self.__protect_critical_keys__
            and isinstance(key, str)
            and hasattr(MutableMapping, key)
        ):
            raise ValueError('Invalid key: "{}"'.format(key))
        self.__dict__[key] = value

    def __setattr__(self, attr: str, value: Any) -> None:
        self[attr] = value

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dict__.keys())

    def __delitem__(self, key: str) -> None:
        del self.__dict__[key]

    def __len__(self) -> int:
        return len(self.__dict__)

    def __repr__(self) -> str:
        if len(self) > 0:
            return "<{}: {}>".format(
                type(self).__name__, ", ".join(sorted(repr(k) for k in self.keys()))
            )
        else:
            return "<{}>".format(type(self).__name__)

    def copy(self) -> "DotDict":
        """Creates and returns a shallow copy of the current DotDict"""
        return type(self)(self.__dict__.copy())

    def to_dict(self) -> dict:
        """Converts current `DotDict` (and any `DotDict`s contained within) to an appropriate nested dictionary."""
        return as_nested_dict(self, dct_class=dict)


def merge_dicts(d1: DictLike, d2: DictLike) -> DictLike:
    """
    Updates `d1` from `d2` by replacing each `(k, v1)` pair in `d1` with the
    corresponding `(k, v2)` pair in `d2`.

    If the value of each pair is itself a dict, then the value is updated
    recursively.

    Args:
        - d1 (MutableMapping): A dictionary to be replaced
        - d2 (MutableMapping): A dictionary used for replacement

    Returns:
        - A `MutableMapping` with the two dictionary contents merged
    """

    new_dict = d1.copy()

    for k, v in d2.items():
        if isinstance(new_dict.get(k), MutableMapping) and isinstance(
            v, MutableMapping
        ):
            new_dict[k] = merge_dicts(new_dict[k], d2[k])
        else:
            new_dict[k] = d2[k]
    return new_dict


def as_nested_dict(
    obj: Union[DictLike, Iterable[DictLike]], dct_class: type = DotDict
) -> Union[DictLike, Iterable[DictLike]]:
    """
    Given a obj formatted as a dictionary, transforms it (and any nested dictionaries)
    into the provided dct_class

    Args:
        - obj (Any): An object that is formatted as a `dict`
        - dct_class (type): the `dict` class to use (defaults to DotDict)

    Returns:
        - A `dict_class` representation of the object passed in
    ```
    """
    if isinstance(obj, (list, tuple, set)):
        return type(obj)([as_nested_dict(d, dct_class) for d in obj])
    elif isinstance(obj, (dict, DotDict)):
        # instantiate the dict and call update because if a dotdict contains a key called
        # `update`, then calling update in __init__ becomes impossible
        new_dict = dct_class()
        new_dict.update({k: as_nested_dict(v, dct_class) for k, v in obj.items()})
        return new_dict
    return obj


class CompoundKey(tuple):
    pass


def dict_to_flatdict(dct: dict, parent: CompoundKey = None) -> dict:
    """Converts a (nested) dictionary to a flattened representation.

    Each key of the flat dict will be a CompoundKey tuple containing the "chain of keys"
    for the corresponding value.

    Args:
        - dct (dict): The dictionary to flatten
        - parent (CompoundKey, optional): Defaults to `None`. The parent key
        (you shouldn't need to set this)

    Returns:
        - dict: A flattened dict
    """

    items = []  # type: list
    parent = parent or CompoundKey()
    for k, v in dct.items():
        k_parent = CompoundKey(parent + (k,))
        if isinstance(v, dict):
            items.extend(dict_to_flatdict(v, parent=k_parent).items())
        else:
            items.append((k_parent, v))
    return dict(items)


def flatdict_to_dict(dct: dict, dct_class: type = None) -> MutableMapping:
    """Converts a flattened dictionary back to a nested dictionary.

    Args:
        - dct (dict): The dictionary to be nested. Each key should be a
        `CompoundKey`, as generated by `dict_to_flatdict()`
        - dct_class (type, optional): the type of the result; defaults to `dict`

    Returns:
        - MutableMapping: A `MutableMapping` used to represent a nested dictionary
    """

    result = (dct_class or dict)()
    for k, v in dct.items():
        if isinstance(k, CompoundKey):
            current_dict = result
            for ki in k[:-1]:
                current_dict = current_dict.setdefault(  # type: ignore
                    ki, (dct_class or dict)()
                )
            current_dict[k[-1]] = v
        else:
            result[k] = v

    return result
