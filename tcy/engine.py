import regex
import typing
import tcy.utils as utils
import tcy.expression
from ruamel.yaml.scalarstring import DoubleQuotedScalarString


# Regular Expression Constants
regex_capture_key           = regex.compile(r"^\$\w*$")
regex_instring_expansions   = regex.compile(r"\$\((([-\s\w.$*]|(\((?:(?2)|\s)*\))|(\"(?:[^\"\\]|\\.)*\")|(\'(?:[^\'\\]|\\.)*\'))+)\)")
regex_outstring_expansions  = regex.compile(r"\$\((\s*[-\w.:]([^()\"\']|(?&R))*)\)|\$(?=[-\w.:]|\(\s*[^-\w.:])((?&R)+)(?(DEFINE)(?<R>[-\w.:$*]|\((?:[^()\"\']|(?&R))*\)|\"(?:[^\"\\]|\\.)*\"|\'(?:[^\'\\]|\\.)*\'))")
regex_parts_in_path         = regex.compile(r"([^\s.,()\"\']|\(((?1)|[\s,.])*\)|\"(?>[^\\\"]|\\.)*\"|'(?>[^\\\']|\\.)*')+|(?<=\.)\s*(?=\.)|\(\)")
regex_calls_in_part         = regex.compile(r"(?<=[^\s])\s*\(([^()\"\']|\((?1)*\)|\"(?>[^\\\"]|\\.)*\"|'(?>[^\\\']|\\.)*')*\)\s*$")
regex_arguments_in_call     = regex.compile(r"(?>[^,()\"\']|\((?>(?R)|[,\s])*\)|\"(?>[^\\\"]|\\.)*\"|'(?>[^\\\']|\\.)*')+|(?<=,|^])(?=\s*(?:,|$))")
regex_is_regex              = regex.compile(r"^(?!\*$).*[\\+*\.()\[\]{}].*$")


# Value type used when doing multiplexing
# Contains a list of individual EvaluationStacks for each individual expression
class BatchResult:
    def __init__(self, engines) -> None:
        self.engines = engines
    @property
    def results(self):
        return [v.data for v in self.engines]


# Class to keep track of all evaluations happening.
# Note: _accumulator is a list, whose last value is the one all processing is made with
class Resolution:
    def __init__(self, root: dict = {}, name: str = "dictionary", arguments: dict = {}):
        self._name              = name
        self._root              = root
        self._accumulator       = []
        self._location_stack    = []
        self._arguments         = [arguments] if arguments else []
    @property
    def data(self):
        return self._accumulator[-1] if self._accumulator else None
    @property
    def location(self):
        return ".".join([str(v) for v in self._location_stack[-1]])
    @property
    def location_stack(self):
        return [".".join([str(v) for v in location]) for location in self._location_stack]
    @property
    def arguments(self):
        return utils.combine_dicts(*self._arguments)
    def push(self, value, added_location="?", *new_arguments, **new_keyword_arguments):
        result                  = Resolution(self._root, self._name)
        result._accumulator     = [*self._accumulator, value]
        result._location_stack  = [*self._location_stack[:-1], [*self._location_stack[-1], added_location]]
        result._arguments       = [*self._arguments, utils.combine_dicts(*new_arguments, new_keyword_arguments)]
        return result
    def set(self, value):
        result                  = Resolution(self._root, self._name)
        result._accumulator     = [*self._accumulator[:-1], value]
        result._location_stack  = self._location_stack
        result._arguments       = self._arguments
        return result
    def call(self, resolution):
        result                  = Resolution(self._root, self._name)
        result._accumulator     = [*self._accumulator, resolution.data]
        result._location_stack  = [*self._location_stack, resolution._location_stack[-1]]
        result._arguments       = [*self._arguments, resolution.arguments]
        return result
    def reference_at(self, other_resolution, added_location = None):
        added_location = [added_location] if added_location else []
        result                  = Resolution(self._root, self._name)
        result._accumulator     = self._accumulator
        result._location_stack  = [*self._location_stack, [*other_resolution._location_stack[-1], added_location]]
        result._arguments       = self._arguments
        return result
    def pop(self):
        if len(self._accumulator) == 0:
            return None
        result                  = Resolution(self._root, self._name)
        result._accumulator     = self._accumulator[:-1]
        result._location_stack  = [self._location_stack[:-1], self._location_stack[-1][:-1]]
        result._arguments       = self._arguments  # Don't pop arguments
        return result
    def call_root(self):
        result                  = Resolution(self._root, self._name)
        result._accumulator     = [self._root]
        result._location_stack  = [*self._location_stack, [self._name]]
        result._arguments       = self._arguments
        return result
    def call_arguments(self):
        result                  = Resolution(self._root, self._name)
        result._accumulator     = [self.arguments] # Use the combined dictionary
        result._location_stack  = [*self._location_stack, ["<arguments>"]]
        result._arguments       = self._arguments
        return result

    # Converts batch results to the list of results
    def finalize(self, batch_results_also=False):
        if isinstance(self.data, Resolution):
            return self.data.finalize()
        result                  = Resolution(self._root, self._name)
        result._accumulator     = self._accumulator
        if batch_results_also and isinstance(self.data, BatchResult):
            result._accumulator[-1] = [engine.finalize(batch_results_also).data for engine in self.data.engines]
        result._location_stack  = self._location_stack
        result._arguments       = self._arguments
        return result

    # Accesses "attribute"
    def indirect(self, key, error_method=Exception, key_evaluation_callback=None):

        # Distinguish between normal keys and evaluated keys (i.e. of type 'Resolution')
        key_value = key.data if isinstance(key, Resolution) else key

        # Ensures, that the key has been evaluated
        def ensure_evaluated_key():
            nonlocal key
            nonlocal key_value
            nonlocal key_evaluation_callback
            if key_evaluation_callback:
                key                     = key_evaluation_callback(key)
                key_value               = key.data if isinstance(key, Resolution) else key
                key_evaluation_callback = None
                return True
            return False

        # Handle the case where the current value is None
        if self.data is None:
            return utils.raise_error(error_method, f"Cannot access key '{key_value}' in '{self.location}' = None")

        # If the current value is a resolution itself, continue inside this resolution
        elif isinstance(self.data, Resolution):
            return self.call(self.data).indirect(key, error_method, key_evaluation_callback)

        # Handle access to dicts
        elif isinstance(self.data, dict):

            # A simple asterisk gives you all values regardless of key
            if key == "*":  # Asterisk only works on literal "*", not expanded strings equal to "*"
                return self.push(
                    BatchResult([self.push(v, k) for k, v in self.data.items()])
                    , key_value
                )

            # Check if the key is in the dictionary
            if isinstance(key_value, typing.Hashable):
                if key_value in self.data:
                    return self.push(self.data[key_value], key_value)

            # Test for capture keys
            capture_keys = [
                match.group()
                for k in self.data.keys()
                if isinstance(k, str) and (match := regex_capture_key.match(k))
            ]

            # Shortcut: Only one capture key and that ones is even unnamed/discarded
            if len(capture_keys) == 1:
                if len(capture_keys[0]) == 1:  # Handle the case where the user just supplies a dollar in order to discard the argument
                    return self.push(self.data[capture_keys[0]], capture_keys[0])

            # Can we evaluate the key?
            if ensure_evaluated_key():

                # Now, Handle Indirection using a batch result -> yield a batch result
                if isinstance(key_value, BatchResult):
                    return self.push(
                        BatchResult([
                            result
                            for engine in key_value.engines
                            if (result := self.indirect(engine.data, None))
                        ])
                        , key_value
                    )

                # Handle lists as keys
                adapted_key_value = key_value
                if isinstance(key_value, list):
                    adapted_key_value = tuple(adapted_key_value)

                # Maybe now, check again if the key is in the dictionary
                if isinstance(adapted_key_value, typing.Hashable):
                    if adapted_key_value in self.data:
                        return self.push(self.data[adapted_key_value], key_value)


            # Check if the access uses a regular expression
            if isinstance(key, str) and regex_is_regex.match(key_value):
                try:
                    key_regex       = regex.compile(key_value)
                    return self.push(
                        BatchResult([
                            self.push(v, k, match.groupdict() or dict(enumerate(match.groups())))
                            for k, v in self.data.items()
                            if (match := key_regex.match(k))
                        ])
                        , key_value
                    )
                except Exception as e:
                    return utils.raise_error(error_method, f"Key '{key_value}' is not a valid regular expression: {e}")

            # Handle every other case
            if len(capture_keys) == 0:
                return utils.raise_error(error_method, f"No key '{key_value}' found in dictionary '{self.location}'")
            elif len(capture_keys) > 1:
                return utils.raise_error(
                    error_method
                    , f"More than one capture key in '{self.location}' ('"
                    + "', '".join(capture_keys)
                    + "')")
            elif isinstance(key, Resolution):
                return self.push(self.data[capture_keys[0]], capture_keys[0], {capture_keys[0][1:]: key.reference_at(self, capture_keys[0])})
            else:
                return self.push(self.data[capture_keys[0]], capture_keys[0], {capture_keys[0][1:]: self.push(key, capture_keys[0])})

        # From this point on, fully evaluate the key
        ensure_evaluated_key()

        # Handle Indirection using a batch result -> yield a batch result
        if isinstance(key_value, BatchResult):
            return self.push(
                BatchResult([
                    result
                    for engine in key_value.engines
                    if (result := self.indirect(engine.data, None))
                ])
                , key_value
            )

        # Handle Access to Lists
        elif isinstance(self.data, list) or isinstance(self.data, tuple):

            # Accessing an index with an integer yields the element
            if isinstance(key_value, int):
                if 0 <= key_value < len(self.data) or 0 > key_value >= -len(self.data):
                    value = self.data[key_value]
                    if isinstance(value, Resolution):
                        return value
                    return self.push(value, key_value)
                return utils.raise_error(error_method, f"Index '{key_value}' is out of range for list/tuple '{self.location}'.")

            # A simple asterisk turns the list into a batch result
            elif key_value == "*":
                return self.push(
                    BatchResult([
                        self.push(v, i, {"__index": i})
                        for i, v in enumerate(self.data)
                    ])
                    , key_value
                )

            # Accessing the list otherwise does multiplexing and returns a list of return values
            else:
                return self.push(
                    BatchResult([
                        result
                        for i, v in enumerate(self.data)
                        if (result := self.push(v, i, {"__index": i}).indirect(key_value, None))
                    ])
                    , key_value
                )

        # Handle access to batch results
        elif isinstance(self.data, BatchResult):
            return self.push(
                BatchResult([
                    result
                    for engine in self.data.engines
                    if (result := engine.indirect(key_value, None))
                ])
                , key_value
            )

        # Handle access to strings
        elif isinstance(self.data, str):
            # When the key is a regular expression, try to match the accumulator with it
            if isinstance(key_value, str):
                try:
                    regular_expression = regex.compile(key_value)
                except Exception as e:
                    return utils.raise_error(error_method, f"Key '{key_value}' is not a valid regular expression: {e}")
                return self.push(
                    BatchResult([
                        self.push(
                            match.groupdict() or (match.groups() if len(match.groups()) > 0 else match.group())
                            , i
                        )
                        for i, match in enumerate(regular_expression.finditer(self.data))
                    ])
                    , key_value
                )
            return utils.raise_error(error_method, f"Cannot access string '{self.location}' with key type '{type(key_value)}', expected search item")

        return utils.raise_error(error_method, f"Cannot access key '{key_value}' in '{self.location}' = '{type(self.data)}({self.data})'")


    # Resolves the supplied path given the supplied indirection accumulator and the supplied arguments
    def resolve(self, path:str, error_method=Exception, evaluate_fully=False):

        # Check origin of reference...

        # The name of the current section?
        if path == ".":
            return self.pop()

        # Convert function-style calls to path parts
        path = regex_parts_in_path.sub(
            lambda part:
                regex_calls_in_part.sub(
                    lambda call:
                        ".("
                        + ").(".join([
                        arg.strip() or "null"
                        for arg in regex_arguments_in_call.findall(call.group().strip()[1:-1])
                        ])
                        +")"
                    , part.group()
                )
            , path
        )

        # 1. Reference relative to parent
        if path.startswith("."):
            path    = path[1:]
            result  = self.pop()
            while path.startswith("."):
                if new_result := result.pop():
                    path    = path[1:]
                    result  = new_result
                else:
                    return utils.raise_error(error_method, f"Cannot indirect upwards from '{result.location}', as it's already the root.")

        # 2. Reference to global namespace?
        elif path.startswith(":"):
            path    = path[1:]
            result  = self.call_root()

        # 3. Reference to arguments
        else:
            result  = self.call_arguments()

        # Resolve the path part by part
        while (part := regex_parts_in_path.match(path)) is not None:

            # Set the path to everything after this match
            path    = path[part.span()[1]:].lstrip()

            # If key is empty, that means, there are two dots following each other
            if part := part.group():

                # Get rid of matching parentheses
                if part[0] == "(" and part[-1] == ")":
                    part = part[1:-1].strip()

                # Callback passed to indirect in order to evaluate the key
                def evaluate_part(part):
                    nonlocal self
                    return self.evaluate(False, error_method, value_only=part)

                # Evaluate the current value
                result  = result.evaluate(error_method)

                # So that we can do one step of indirection
                result  = result.indirect(
                    utils.string_to_value(part)
                    , error_method
                    , key_evaluation_callback=evaluate_part
                )

            # Otherwise: Handle empty matches, they indicate two subsequent dots -> go up one level
            elif new_result := result.pop():
                result = new_result
            else:
                return utils.raise_error(error_method, f"Cannot indirect upwards from '{result.location}', as it's already the root.")

            # Break out of the loop, if we parsed the whole path
            if not path:
                break

            # Handle the dot at the end (resolves to the name of the key we're in)
            if path == ".":
                if not isinstance(result.data, BatchResult):
                    result  = result.pop().push(result._location_stack[-1][-1])
                else:
                    result = self.push(BatchResult([
                        engine.pop().push(engine._location_stack[-1][-1])
                        for engine in result.data.engines
                    ]))
                break

            # Just take away the path separator
            elif path[0] == ".":
                path    = path[1:]

            else:
                return utils.raise_error(error_method, f"Invalid path format at '{result.location}': {path}")

        # Make sure, we get the actual definition of the value
        result = result.finalize()

        # Fully evaluate the result?
        if evaluate_fully:
            result = result.evaluate(error_method, full=True).finalize(batch_results_also=True)

        return result


    # Helper function that expands expressions of the form ${...} int the supplied value
    def evaluate(self, error_method=Exception, full=False, value_only=utils.NotSet()):

        # Determine the value to be expanded (default is the current value of the accumulator)
        value       = self.data if isinstance(value_only, utils.NotSet) else value_only
        value_only  = not isinstance(value_only, utils.NotSet)

        # Is the value a string? -> Expand expansion groups in string
        if isinstance(value, str) and value != "":

            # Determine, whether inside a string or not
            string_mode = False
            if isinstance(value, DoubleQuotedScalarString):
                string_mode = True
            elif value[0] in ["'", '"'] and value[-1] in ["'", '"']:
                string_mode = True
                value       = value[1:-1]
            regex_expansions = regex_instring_expansions if string_mode else regex_outstring_expansions

            # Class representing a result part
            class ResultToken:
                def __init__(self, value:str|Resolution, verbatim:bool, expanded:bool):
                    self.value         = value
                    self.is_verbatim   = verbatim
                    self.is_expanded   = expanded
                @staticmethod
                def verbatim(value): return ResultToken(value, True, False)
                @staticmethod
                def expanded(value): return ResultToken(value, False, True)
                @staticmethod
                def formatted(value): return ResultToken(value, True, True)

            # Iterate over the string and find the expansion groups
            result: [ResultToken]   = []  # Lists of all tokens of this expressions
            while (match := regex_expansions.search(value)) is not None:

                # Process prefix before match
                prefix = value[0:match.span()[0]]
                if not string_mode:
                    prefix = prefix.strip()
                if prefix:
                    result.append(ResultToken.verbatim(prefix))

                # Strip the match from the input
                value       = value[match.span()[1]:]

                # Determine content
                content     = match.group(1) or match.group(3)

                # Resolve the expression
                resolution  = self.resolve(content.strip())

                # Add the result
                result.append(ResultToken.expanded(resolution))

            # Process string suffix
            if not string_mode:
                value = value.strip()
            if value:
                result.append(ResultToken.verbatim(value))

            # Postprocess list of parts
            if result == []:
                return None if value_only else self.set(None)
            elif string_mode:
                result = "".join([
                    v.value
                    if v.is_verbatim else
                    str(v.value.evaluate(error_method, full=True).finalize(True).data)
                    for v in result
                ])
                return result if value_only else self.set(result)
            elif len(result) == 1:
                if result[0].is_verbatim:
                    if value_only and not result[0].is_expanded:
                        return result[0].value
                    else:
                        return self.set(result[0].value)
                elif full:
                    return result[0].value.evaluate(error_method, full=True)
                else:
                    return result[0].value
            else:
                # Convert all result tokens into python expression
                expression = " ".join([
                    v.value
                    if v.is_verbatim else
                    repr(v.value.evaluate(error_method, full=True).finalize(True).data)
                    for v in result
                ])
                try:
                    return self.set(eval(expression))  # Evaluate the expression
                except Exception as e:
                    return utils.raise_error(error_method, f"Error while evaluating expression '{expression}': {e}")

        # Expand on the parts of dictionaries only if nested shall be expanded
        elif full and isinstance(value, dict):
            return self.set({
                self.push(k, k).evaluate(error_method, True)
                : self.push(v, k).evaluate(error_method, True)
                for k, v in value.items()
            })

        # Expand the parts of lists only if nested shall be expanded
        elif full and isinstance(value, list):
            return self.set([self.push(v, i).evaluate(error_method, True) for i, v in enumerate(value)])

        # Expand the result inside a batch result
        elif full and isinstance(value, BatchResult):
            return self.set(BatchResult([
                engine.evaluate(error_method, True)
                for engine in value.engines
            ]))

        return value if value_only else self.set(value)

