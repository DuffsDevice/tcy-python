import tcy.engine as engine
import tcy.utils as utils

def access(
    dictionary: dict
    , path: str
    , *arguments_dicts
    , fallback=utils.NotSet()
    , check=None
    , evaluate_fully: bool=True
    , error_method=Exception
    , logging_name: str="dictionary"
    , **arguments_keywords
):
    """
    Access a (possibly nested) key within the supplied dictionary.
    The key is a string, while dots "." allow you to refer to keys within the values of keys.
    The value can be automatically checked for certain criteria by setting the parameter "check".
    Values retrieved from the dictionary may facilitate expansion patterns of the form "${...}".
    They are resolved using the expansion information inside additionally supplied dictionaries and keywords.
    Note, that ${self.XYZ} may always be used to refer to the dictionary itself (if self is not explicitly set
    to something else by the supplied expansion information).
    :param dictionary:          The dictionary in which to look up the supplied 'path_to_key'
    :param path:                Either a string (use dots "." to refer to keys within the values of keys)
    :param fallback:            Supply anything, including None, if you'd like to this function to return
                                a fallback value on error
    :param check:               Supply one of
                                 - True: Assert the value evaluates to something non-False
                                 - list: Assert the value evaluates to a non-empty list
                                 - dict: Assert the value evaluates to a non-empty dictionary
                                 - <something callable>: Pass your own assertion predicate (must return bool)
    :param evaluate_fully:       If the value that is queried is itself a dictionary or list:
                                Whether to expand the contents/elements of the dictionary/list
    :param error_method:        Function to be used to signal assertion errors.
                                You may pass "Exception" or an Exception-derived class
    :param logging_name:        Name of the dictionary in order to improve error messages
    :param arguments_dicts:     List of dictionaries containing information to be used in ${...} expressions
                                by the value once retrieved. In case of duplicate keys, the first one wins.
    :param arguments_keywords:  List of keyword arguments to be used in ${...} expressions
    """

    # Combine all evaluation information into one dict
    arguments   = utils.combine_dicts(*reversed(arguments_dicts), arguments_keywords)

    # 1. Resolve the path
    value = None
    # try:
    value = engine.Resolution(
            dictionary
            , logging_name
            , arguments
            ).resolve(
                ":" + path  # Resolve the path relative to the root of the dicitonary
                , evaluate_fully=evaluate_fully
            ).data
    try:
        pass
    except Exception as e:
        if not isinstance(fallback, utils.NotSet):
            return fallback
        error = str(e) or f'Unknown exception "{type(e)}"'
        error = f'Could not resolve attribute "{path}" in {logging_name}: {error}'
        return utils.raise_error(error_method, error) or (
            None if isinstance(fallback, utils.NotSet) else fallback
        )

    # 3. Check the value
    if check == True and not value:
        error   = "Only non-empty values allowed!"
    elif (check == list or check == dict) and not value:
        error   = "Expected at least one list/subsection entry!"
    elif callable(check) and not check(value):
        error   = f"Validation was {check}"

    # 4. Return value if all checks passed
    else:
        return value

    # 5. Issue an error
    error = f'Key value "{logging_name}".{path} = "{value}" is not valid: {error}'
    return raise_error(error_method, error) or (
        None if isinstance(fallback, NotSet) else fallback
    )


# Identical working principle as access_dict, but allows to raise an attribute-specific error
# def issue_dict_error(
#     dictionary
#     , path
#     , error_reason: str = ""
#     , *arguments_dicts
#     , error_method=Exception
#     , logging_name: str="dictionary"
#     , **arguments_keywords
# ):
#     # Normalize path to list recursive keys
#     if isinstance(path, str):
#         path = path.split(".")

#     # Combine all evaluation information into one dict
#     arguments       = combine_dicts({"self": dictionary}, *reversed(arguments_dicts), arguments_keywords)
#     resolved        = Indirection()
#     error_reason    = ": " + error_reason if error_reason else "!"
#     value           = ""
#     try:
#         resolved    = resolve(path, Indirection(dictionary, logging_name), arguments)
#     except Exception as e:
#         pass

#     # Evaluate special patterns ${...}?
#     if arguments:
#         value = f' = "{expand_value(value, arguments)}", expanded from "{value}"'
#     else:
#         value = f' = "{value}"'
#     message = f'Key "{logging_name}".{".".join(path)}{value} is not valid{error_reason}'

#     # Issue error
#     if error_method is not None:
#         if inspect.isclass(error_method) and issubclass(error_method, Exception):
#             raise error_method(message)
#         elif callable(error_method):
#             error_method(message)
