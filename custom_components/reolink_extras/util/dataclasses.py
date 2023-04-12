""""DataClass helpers"""

import dataclasses
import inspect
from typing import Mapping, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import cast

C = TypeVar("C")


_sig_cache: dict[type, set[str]] = {}


def unpack_from_json(cls: type[C], json: Mapping[str, any] = None, /, **kwargs: any):
    """ "unpack" passed json into dataclass"""

    # we use the functions non dataclass assert asap
    fields = dataclasses.fields(cls)
    if isinstance(json, Mapping):
        kwargs.update(json)
    json = kwargs
    kwargs = None
    kw_field = None
    known = set(json.keys())
    for field in fields:
        key: str
        if (
            field not in known
            and (key := field.metadata.get("json")) is not None
            and key in known
        ):
            known.remove(key)
            json[field.name] = json.pop(key)
            known.add(field.name)
        if (
            field.name in known
            and (
                transform := field.metadata.get(
                    "trans", field.metadata.get("transform")
                )
            )
            and callable(transform)
        ):
            json[field.name] = transform(json[field.name])
        if kw_field is None and (
            field.name == "kwargs" or bool(field.metadata.get("kwargs"))
        ):
            kw_field = field.name
            if field.name in known:
                __dict = json[field.name]
                if TYPE_CHECKING:
                    __dict = cast(dict, __dict)
                kwargs = __dict
    if (sig := _sig_cache.get(cls)) is None:
        sig = _sig_cache.setdefault(
            cls, ({key for key in inspect.signature(cls).parameters})
        )
    kwargs_keys = known - sig
    if len(kwargs_keys) and kw_field:
        if kwargs is None:
            kwargs = {}
        for key in kwargs_keys:
            known.remove(key)
            kwargs[key] = json.pop(key)
        if kw_field not in known and kw_field in sig:
            json[kw_field] = kwargs
    return cls(**{key: json[key] for key in known.intersection(sig)})
