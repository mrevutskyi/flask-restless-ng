from collections import namedtuple
from typing import Dict

from .typehints import Model

#: A tuple that stores information about a created API.
#:
#: The elements are, in order,
#:
#: - `collection_name`, the name by which a collection of instances of
#:   the model exposed by this API is known,
#: - `blueprint_name`, the name of the blueprint that contains this API,
#: - `serializer`, the subclass of :class:`Serializer` provided for the
#:   model exposed by this API.
#: - `primary_key`, the primary key used by the model
#: - `url_prefix`, the url prefix to use for the collection
#:
APIInfo = namedtuple('APIInfo', ['collection_name', 'blueprint_name', 'serializer', 'primary_key', 'url_prefix'])


_registry: Dict[Model, APIInfo] = {}


def add(model: Model, api_info: APIInfo):
    _registry[model] = api_info
