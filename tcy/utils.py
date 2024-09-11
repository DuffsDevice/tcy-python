import functools
import inspect
import ruamel.yaml as yaml

# Magic type to be distict from every other possible value
class NotSet:
    pass

# Combines the supplied dictionaries (last occurrence of a key wins)
def combine_dicts(*arguments_dicts):
    return functools.reduce(
        lambda a, b: {**a, **b}
        , arguments_dicts
        , {}
    )

# Converts a string to the value that it would have as when it would be written in yaml
def string_to_value(value):
    if value == "*":
        return value
    try:
        return yaml.load(f"v: {value}", )["v"]
    except:
        return value

# Raises an error using the supplied error method
def raise_error(error_method, error):
    if error_method is not None:
        if inspect.isclass(error_method) and issubclass(error_method, Exception):
            raise error_method(error)
        elif callable(error_method):
            error_method(error)
    return None