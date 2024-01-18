import tcy
import yaml

with open("test.yaml") as file:
    my_dict = yaml.safe_load(file.read())

# Example 1: Access attribute
result = tcy.access(my_dict, "my_test")
print("Example 1:", result)


# Example 2: Nested Variable
result = tcy.access(my_dict, "my_dictionary.my_key")
print("Example 2:", result)


# Example 3: Access attribute that depends on arguments
result = tcy.access(my_dict, "my_message", name_to_print="World")
print("Example 3:", result)


# Example 4: Same, but with a dictionary
argument_dict    = {"name_to_print": "World", "first_word": "Hello"}
result = tcy.access(my_dict, "my_message", argument_dict)
print("Example 4:", result)


# Example 5: Variable in Path
result = tcy.access(my_dict, "my_variable_test.${my_key}")
print("Example 5:", result)


# Example 6: More complex
result = tcy.access(my_dict, "my_config.my_paths.0")
print("Example 6:", result)


# Example 7: Functions!
result = tcy.access(my_dict, "fac.5")
print("Example 6:", result)