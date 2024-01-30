import functools
import regex
import inspect
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes=True

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


# Regular Expression Constants
regex_capture_key           = regex.compile(r"^\$\w+$")
regex_instring_expansions   = regex.compile(r"\$\{(:?(?3))(?::([^}]*))?\}(?:$^((?>[^:$\"'[\]{}]+|\$?\{(?:(?3)|:)+\}|\$(?!\{)|\"(?:[^\\\"]|\\.)*\"|'(?:[^\\\']|\\.)')*))?")
regex_outstring_expansions  = regex.compile(r"(?:\$\{(:?(?4))(?::([^}]*))?\}|(?<!\w)\$([:.\w][.\w]*))(?:$^((?>[^:$\"\'[\]{}]+|\$?\{(?:(?4)|:)+\}|\$(?!\{)|\"(?:[^\\\"]|\\.)*\"|\'(?:[^\\\']|\\.)\')*))?")
regex_path_indirections     = regex.compile(r"((?:[^.:$\"'[\]{}]+|\$?\{(?1)\}|(?<!\w)\$(?!\{)|\"(?:[^\\\"]|\\.)*\"|'(?:[^\\\']|\\.)*')+)|(?<=\.)(?=\.)")
regex_is_regex              = regex.compile(r"^(?!\*$).*[\\+*\.()\[\]{}].*$")


# Value type used when doing multiplexing
# Contains a list of individual EvaluationStacks for each individual expression
class BatchResult:
    def __init__(self, accumulators) -> None:
        self.accumulators = accumulators
    @property
    def results(self):
        return [v.data for v in self.accumulators]


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
    def push(self, value, added_location="?", *new_arguments, **new_keyword_arguments):
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

    # Converts batch results to the list of results
    def finalize(self):
        result              = PyamlEngine(None, None)
        result._accumulator = self._accumulator
        if isinstance(result._accumulator[-1], BatchResult):
            result._accumulator[-1] = [accumulator.finalize().data for accumulator in self.data.accumulators]
        result._path        = self._path
        result._arguments   = self._arguments
        return result


    # Accesses "attribute"
    def indirect(self, key, error_method=Exception):

        # Handle the case where the current value is None
        if self.data is None:
            return raise_error(error_method, f"Cannot access key '{key}' in '{self.location}' = None")

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
                        if (result := self.push(v, i).indirect(key, None))
                    ])
                    , key
                )

        # Handle access to batch results
        if isinstance(self.data, BatchResult):
            return self.push(
                BatchResult([
                    result
                    for accumulator in self.data.accumulators
                    if (result := accumulator.indirect(key, None))
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
                            self.push(v, k, match.groupdict() or dict(enumerate(match.groups())))
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
            while path[0] == ".":
                if new_result := result.pop():
                    path    = path[1:]
                    result  = new_result
                else:
                    return raise_error(error_method, f"Cannot indirect upwards from '{result.location}', as it's already the root.")

        # 2. Reference to global namespace?
        elif path[0] == ":":
            path    = path[1:]
            result  = self.push_root()

        # 3. Reference to arguments
        else:
            result  = self.push_arguments()

        # Resolve the path key by key
        while (key := regex_path_indirections.match(path)) is not None:

            # Set the path to everything after this match
            path    = path[key.span()[1]:]

            # If key is empty, that means, there are two dots following each other
            if key:
                key     = self.expand(False, error_method, value=string_to_value(key.group()))
                result  = result.indirect(key, error_method)  # Do one step of indirection

            # Otherwise: Handle empty matches, they indicate two subsequent dots -> go up one level
            elif new_result := result.pop():
                result = new_result
            else:
                return raise_error(error_method, f"Cannot indirect upwards from '{result.location}', as it's already the root.")

            # Break out of the loop, if we parsed the whole path
            if not path:
                break

            # Handle the dot at the end (resolves to the name of the key we're in)
            if path == ".":
                if not isinstance(result.data, BatchResult):
                    result  = result.pop().push(result._path[-1])
                else:
                    result = self.push(BatchResult([
                        accumulator.pop().push(accumulator._path[-1])
                        for accumulator in result.data.accumulators
                    ]))
                break

            # Just take away the path separator
            elif path[0] == ".":
                path    = path[1:]

            else:
                return raise_error(error_method, f"Invalid path format at '{result.location}': {path}")

        # Make sure, batch results are converted to the list of results
        return result.finalize()


    # Helper function that expands expressions of the form ${...} int the supplied value
    def expand(self, error_method=Exception, expand_nested=False, value=NotSet()):

        # Determine the value to be expanded (default is the current value of the accumulator)
        if isinstance(value, NotSet):
            value = self.data

        # Is the value a string? -> Expand expansion groups in string
        if isinstance(value, str):

            # Determine, whether inside a string or not
            string_mode         = False
            if isinstance(value, DoubleQuotedScalarString):
                string_mode     = True
            elif value[0] in ["'", '"'] and value[-1] in ["'", '"']:
                string_mode     = True
                value           = value[1:-1]

            # Expand every expansion group
            result              = []  # Lists of all tokens of this expressions; format: [(<value>, <is-expanded>)]
            regex_expansions    = regex_instring_expansions if string_mode else regex_outstring_expansions
            while (match := regex_expansions.search(value)) is not None:

                # Process prefix before match
                prefix = value[0:match.span()[0]]
                if not string_mode:
                    prefix = prefix.strip()
                if prefix:
                    result.append((prefix, False))

                # Strip the match from the input
                value = value[match.span()[1]:]

                # Does the expansion have a format?
                expression = match.group(1) or match.group(3)  # 1st group is the explicit style, 3rd group is the implicit one
                if not expression:
                    continue

                # Evaluate the expression
                expression_result = self.resolve(expression.lstrip()).expand(error_method)

                # Shall the result be formatted in a specific way?
                if format := match.group(2):  # Match group 2 is defined as the formatting specifier, e.g. as in {value:03}
                    expression_result = ("{0:" + format + "}").format(expression_result)

                # Add the result
                result.append((expression_result, True))

            # Process string suffix
            if not string_mode:
                value = value.strip()
            if value:
                result.append((value, False))

            # Postprocess list of parts
            if result == []:
                result = None
            elif string_mode:
                result = "".join([str(v[0]) for v in result])
            elif len(result) == 1:
                result = result[0][0]
            else:
                expression = " ".join([(repr if v[1] else str)(v[0]) for v in result])
                try:
                    result = eval(expression)  # Evaluate the result
                except Exception as e:
                    return raise_error(error_method, f"Error while evaluating expression '{expression}': {e}")

        # Expand on the parts of dictionaries only if nested shall be expanded
        elif expand_nested and isinstance(value, dict):
            result = {
                self.push(k, k).expand(error_method, True)
                : self.push(v, k).expand(error_method, True)
                for k, v in value.items()
            }

        # Expand the parts of lists only if nested shall be expanded
        elif expand_nested and isinstance(value, list):
            result = [self.push(v, i).expand(error_method, True) for i, v in enumerate(value)]

        # Otherwise, return the input
        else:
            result = value

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

    # 1. Resolve the path
    engine      = PyamlEngine(dictionary, logging_name, arguments)
    try:
        engine = engine.resolve(":" + path)  # Resolve the path relative to the whole dictionary
    except Exception as e:
        if not isinstance(fallback, NotSet):
            return fallback
        error = str(e) or f'Unknown exception "{type(e)}"'
        error = f'Could not resolve attribute "{path}" in {logging_name}: {error}'
        return raise_error(error_method, error) or (
            None if isinstance(fallback, NotSet) else fallback
        )

    # 2. Evaluate special patterns ${...} with evaluation information
    value       = engine.data
    try:
        value = engine.expand(expand_nested=expand_nested)
    except Exception as e:
        error = str(e) or f'Unknown exception "{type(e)}"'
        error = f'Error while expanding value of attribute "{logging_name}.{path}": {error}'
        return raise_error(error_method, error) or (
            None if isinstance(fallback, NotSet) else fallback
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

    # 5. Otherwise: Determine error message
    if engine.data or value:
        if arguments:
            engine.data = f' = "{value}" (from {engine.data})'
        else:
            engine.data = f' = "{engine.data}"'
    else:
        engine.data = ""
    error = f'Key value "{logging_name}".{path}{engine.data} is not valid: {error}'

    # 6. Issue the error
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