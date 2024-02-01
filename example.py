import tcy
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes=True
with open("test.yaml") as file:
    my_dict = yaml.load(file.read())

# Example 1: Access attribute
result = tcy.access(my_dict, "my_test")
print("Example 1:", repr(result))


# Example 2: Nested Variable
result = tcy.access(my_dict, "my_dictionary.my_key")
print("Example 2:", repr(result))


# Example 3: Access attribute that depends on arguments
result = tcy.access(my_dict, "my_message", name_to_print="World")
print("Example 3:", repr(result))


# Example 4: Same, but with a dictionary
argument_dict    = {"name_to_print": "World"}
result = tcy.access(my_dict, "my_message", argument_dict)
print("Example 4:", repr(result))


# Example 5: Variable in Path
result = tcy.access(my_dict, "my_variable_test.${:my_key}")
print("Example 5:", repr(result))


# Example 6: More complex
result = tcy.access(my_dict, "my_config.my_paths.0")
print("Example 6:", repr(result))


# Example 7: Functions!
result = tcy.access(my_dict, "fac.5")
print("Example 6:", repr(result))


# Example 7: Dictionaries and Inheritance!
result = tcy.access(my_dict, "my_derived_class.var1")
print("Example 7:", repr(result))