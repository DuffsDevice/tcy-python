import functools
import regex
import inspect
import yaml

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
    return yaml.safe_load(f"v: {value}")["v"]

# Raises an error using the supplied error method
def raise_error(error_method, error):
    if error_method is not None:
        if inspect.isclass(error_method) and issubclass(error_method, Exception):
            raise error_method(error)
        elif callable(error_method):
            error_method(error)
    return None


# Regular Expression Constants
regex_capture_key       = regex.compile(r"\$[^\$]\.*")
regex_expansion_groups  = regex.compile(r"(?:\$\[(?1)\]|\$\{(?1)\})(?:$^((?>[^$\"'[\]{}]+|\$\$.|\$?(\{(?1)\}|\[(?1)\])|\"[^\"]*\"|'[^']*')*))?")
regex_path_indirections = regex.compile(r"((?:[^.:$\"'[\]{}]+|\$\$.|\$?(?:\{(?:(?1)|[:.])*\}|\[(?:(?1)|[:.])*\])|\"[^\"]*\"|'[^']*')+)|(?=\.)")
regex_escape_pattern    = regex.compile(r"\$[^\$]*\$")
regex_is_regex          = regex.compile(r"^(?!\*$).*[\\+*\.()\[\]{}].*$")
regex_strip_string      = regex.compile(r"^\s*((?:[^$\"'[\]{}]+?|\$\$.|\$?(?:\{(?:(?1))+\}|\[(?:(?1))+\])|\"[^\"]*\"|'[^']*')*?)\s*$")

# Strips the supplied string of unneeded whitespaces
def intelligent_strip(string):
    return regex_strip_string.match(string).group(1)

# Value type used when doing multiplexing
# Contains a list of individual EvaluationStacks for each individual expression
class BatchResult:
    def __init__(self, accumulators) -> None:
        self.accumulators = accumulators
    @property
    def results(self):
        return [v.data for v in self.accumulators]

# Converts batch results to the list of results
def collapse_batch_result_to_list(value):
    if isinstance(value, BatchResult):
        return [collapse_batch_result_to_list(accumulator.data) for accumulator in value.accumulators]
    return value


# Class to keep track of all evaluations happening.
# Note: _accumulator is a list, whose last value is the one all processing is made with
class PyamlEngine:
    def __init__(self, data = NotSet(), location: str = "dictionary", arguments: dict = {}):
        self._accumulator   = None if isinstance(data, NotSet) else [data]
        self._path          = None if isinstance(data, NotSet) else [location]
        self._arguments     = None if isinstance(data, NotSet) else [arguments]
    @property
    def data(self):
        return self._accumulator[-1] if self._accumulator else None
    @property
    def location(self):
        return ".".join([str(v) for v in self._path])
    @property
    def arguments(self):
        return combine_dicts(*self._arguments)
    def push(self, value, added_location, *new_arguments, **new_keyword_arguments):
        result = PyamlEngine(None, None)
        result._accumulator = [*self._accumulator, value]
        result._path        = [*self._path, added_location]
        result._arguments   = [*self._arguments, combine_dicts(*new_arguments, new_keyword_arguments)]
        return result
    def pop(self):
        if len(self._accumulator) == 0:
            return None
        result              = PyamlEngine(None, None)
        result._accumulator = self._accumulator[0:-1]
        result._path        = self._path[0:-1]
        result._arguments   = self._arguments[0:-1]
        return result
    def push_root(self):
        result              = PyamlEngine(None, None)
        result._accumulator = self._accumulator[0:1]
        result._path        = self._path[0:1]
        result._arguments   = self._arguments
        return result
    def push_arguments(self):
        result              = PyamlEngine(None, None)
        result._accumulator = [self.arguments] # Use the combined dictionary
        result._path        = self._path
        result._arguments   = self._arguments
        return result

    # Accesses "attribute"
    def indirect(self, key, error_method=Exception):

        # Handle the case where the current value is None
        if self.data is None:
            return raise_error(error_method, f"Cannot access key '{key}' in '{self.location}' = None")

        # Convert the attribute to the value type has in yaml (e.g. a 4 would be converted to integer, while "4" is a string)
        key = string_to_value(key)

        # Handle Access to Lists
        if isinstance(self.data, list):

            # Accessing an index with an integer yields the element
            if isinstance(key, int):
                if 0 <= key < len(self.data):
                    value = self.data[key]
                    if isinstance(value, PyamlEngine):
                        return value
                    return self.push(value, key)
                return raise_error(error_method, f"Index '{key}' is out of range for list '{self.location}'.")

            # Accessing the list otherwise does multiplexing and returns a list of return values
            else:
                return self.push(
                    BatchResult([
                        result
                        for i, v in enumerate(self.data)
                        if (result := self.push(v, str(i), {"__index": i}).indirect(key, None))
                    ])
                    , key
                )

        # Handle access to batch results
        if isinstance(self.data, BatchResult):
            return self.push(
                BatchResult([
                    result
                    for i, accumulator in enumerate(self.data.accumulators)
                    if (result := accumulator.indirect(key, {"__index": i}), key, None)
                ])
                , key
            )

        # Handle access to strings
        if isinstance(self.data, str):
            # When the key is a regular expression, try to match the accumulator with it
            if isinstance(key, str):
                try:
                    regular_expression = regex.compile(key)
                except Exception as e:
                    return raise_error(error_method, f"Key '{key}' is not a valid regular expression: {e}")
                return self.push(
                    BatchResult([
                        self.push(
                            match.groupdict() or (match.groups() if len(match.groups()) > 0 else match.group())
                            , i
                            , {"__index": i}
                        )
                        for i, match in enumerate(regular_expression.finditer(self.data))
                    ])
                    , key
                )
            return raise_error(error_method, f"Cannot access string '{self.location}' with key type '{type(key)}', expected search item")

        # Handle access to dicts
        if isinstance(self.data, dict):

            # A simple asterisk gives you all values regardless of key
            if key == "*":
                return self.push(
                    BatchResult([
                        self.push(v, k, {"__key": k})
                        for k, v in self.data.items()
                    ])
                    , key
                )

            # Using a regular expression
            elif isinstance(key, str) and regex_is_regex.match(key):
                try:
                    key_regex       = regex.compile(key)
                    return self.push(
                        BatchResult([
                            self.push(
                                v
                                , k
                                , match.groupdict() or dict(enumerate(match.groups()))
                            )
                            for k, v in self.data.items()
                            if (match := key_regex.match(k))
                        ])
                        , key
                    )
                except Exception as e:
                    return raise_error(error_method, f"Key '{key}' is not a valid regular expression: {e}")

            if key in self.data:
                return self.push(self.data[key], key)

            # Test for capture keys
            capture_keys = [
                match.group()
                for k in self.data.keys()
                if isinstance(k, str) and (match := regex_capture_key.match(k))
            ]
            if len(capture_keys) == 0:
                return raise_error(error_method, f"No key '{key}' found in dictionary '{self.location}'")
            elif len(capture_keys) > 1:
                return raise_error(
                    error_method
                    , f"More than one capture key in '{self.location}' ('"
                    + "', '".join(capture_keys)
                    + "')")
            else:
                return self.push(self.data[capture_keys[0]], capture_keys[0], {capture_keys[0][1:]: key})

        return raise_error(error_method, f"Cannot access key '{key}' in '{self.location}' = '{type(self.data)}({self.data})'")


    # Resolves the supplied path given the supplied indirection accumulator and the supplied arguments
    def resolve(self, path:str, error_method=Exception):

        # Check origin of reference...

        # The name of the current section?
        if path == ".":
            return self.push(self._path[-1], "__key")


        # 1. Reference relative to parent
        if path[0] == ".":
            path    = path[1:]
            result  = self.pop()

        # 2. Reference to arguments?
        elif path[0] == ":":
            path    = path[1:]
            result  = self.push_arguments()

        # 3. Reference to global namespace
        else:
            result  = self.push_root()

        # Resolve the path key by key
        while (key := regex_path_indirections.match(path)) is not None:

            # Remove the key from the front of the path
            path    = path[key.span()[1]:]

            # Set key to its string content (with unnecessary whitespaces trimmed from both sides of the string)
            key     = intelligent_strip(key.group())

            # Handle empty matches, they indicate two subsequent dots -> go up one level
            if key:

                # Expand potential variables in this key and do one step of indirection
                result  = result.indirect(self.expand(False, error_method, value=key), error_method)

            # Handle empty matches, they indicate two subsequent dots -> go up one level
            elif new_result := result.pop():
                result = new_result
            else:
                return raise_error(error_method, f"Cannot indirect upwards from '{result.location}', as it's already the root.")

            # Break out of the loop, if we parsed the whole path
            if not path:
                break

            # Is the next key referring to the arguments?
            elif path[0] == ":":
                path    = path[1:]
                result  = result.push_arguments()

            # Handle the dot at the end (resolves to the name of the key we're in)
            elif path == ".":
                path    = ""
                result  = result.pop().push(result._path[-1], "__name")

            # Just take away the path separator
            elif path[0] == ".":
                path    = path[1:]

            else:
                return raise_error(error_method, f"Invalid path format at '{result.location}': {path}")

        return result


    # Helper function that expands expressions of the form ${...} int the supplied value
    def expand(self, error_method=Exception, expand_nested=False, value=NotSet()):

        # Determine the value to be expanded (default is the current value of the accumulator)
        if isinstance(value, NotSet):
            value = self.data
        result = value

        # Is the value a string? -> Expand variables in string
        if isinstance(result, str):

            # Called by regex.sub, whenever an expansion group occours
            def expansion_group_callback(pattern):
                nonlocal result

                # Determine expansion type
                if pattern.group().startswith("${"):
                    result = self.resolve(pattern.group()[2:-1].lstrip()).expand(error_method)
                    result = collapse_batch_result_to_list(result) # Make sure, batch results are converted to the list of results

                elif pattern.group().startswith("$["):
                    expression = self.expand(error_method, value=pattern.group()[2:-1].lstrip())
                    try:
                        result = eval(str(expression))
                    except Exception as e:
                        return raise_error(error_method, f"Error while evaluating expression '{expression}': {e}")


                # If the ${...} expression is equal to value (equal to the whole string), return the empty string,
                # which will lead the call to regex.sub() to return this empty string. Therefore, the assignment
                # four lines below (result = regex.sub...) will resolve to the "or" case and leav the value of "result"
                # as it was, after we assigned it in the beginning of this sub-function.
                # We therefore preserve the datatype of what the ${...} expression resolved to, yay :)
                return "" if pattern.span() == (0, len(value)) else str(result)

            result = regex_expansion_groups.sub(expansion_group_callback, result) or result

        # Otherwise, if nested values shall be expanded, recursively call expand_value on them
        elif expand_nested:
            if isinstance(result, dict):
                result = {
                    self.push(k, k).expand(error_method, True)
                    : self.push(v, k).expand(error_method, True)
                    for k, v in result.items()
                }
            elif isinstance(result, list):
                result = [self.push(v, i).expand(error_method, True) for i, v in enumerate(result)]

        return result


def access(
    dictionary: dict
    , path: str
    , *arguments_dicts
    , fallback=NotSet()
    , check=None
    , expand_nested: bool=True
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
    :param expand_nested:       If the value that is queried is itself a dictionary or list:
                                Whether to expand the contents/elements of the dictionary/list
    :param error_method:        Function to be used to signal assertion errors.
                                You may pass "Exception" or an Exception-derived class
    :param logging_name:        Name of the dictionary in order to improve error messages
    :param arguments_dicts:     List of dictionaries containing information to be used in ${...} expressions
                                by the value once retrieved. In case of duplicate keys, the first one wins.
    :param arguments_keywords:  List of keyword arguments to be used in ${...} expressions
    """

    # Combine all evaluation information into one dict
    arguments   = combine_dicts(*reversed(arguments_dicts), arguments_keywords)

    # 1. Expand the variables in the path
    try:
        path    = PyamlEngine(path, path, arguments).expand(expand_nested=expand_nested)
    except Exception as e:
        error   = str(e) or f'Unknown exception "{type(e)}"'
        error   = f'Error while expanding the path "{logging_name}.{path}": {error}'
        return raise_error(error_method, error) or (
            None if isinstance(fallback, NotSet) else fallback
        )


    # 2. Resolve the path itself
    engine    = PyamlEngine(dictionary, logging_name, arguments).resolve(path)
    try:
        pass
    except Exception as e:
        if not isinstance(fallback, NotSet):
            return fallback
        error = str(e) or f'Unknown exception "{type(e)}"'
        error = f'Could not resolve attribute "{path}" in {logging_name}: {error}'
        return raise_error(error_method, error) or (
            None if isinstance(fallback, NotSet) else fallback
        )

    # 3. Evaluate special patterns ${...} with evaluation information
    value = engine.data
    # try:
    value = engine.expand(expand_nested=expand_nested)
    try:
        pass
    except Exception as e:
        error = str(e) or f'Unknown exception "{type(e)}"'
        error = f'Error while expanding value of attribute "{logging_name}.{path}": {error}'
        return raise_error(error_method, error) or (
            None if isinstance(fallback, NotSet) else fallback
        )

    # 4. Check the value
    if check == True and not value:
        error   = "Only non-empty values allowed!"
    elif (check == list or check == dict) and not value:
        error   = "Expected at least one list/subsection entry!"
    elif callable(check) and not check(value):
        error   = f"Validation was {check}"

    # 5. Return value if all checks passed
    else:
        return value

    # 6. Otherwise: Determine error message
    if engine.data or value:
        if arguments:
            engine.data = f' = "{value}" (from {engine.data})'
        else:
            engine.data = f' = "{engine.data}"'
    else:
        engine.data = ""
    error = f'Key value "{logging_name}".{path}{engine.data} is not valid: {error}'

    # 7. Issue the error
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