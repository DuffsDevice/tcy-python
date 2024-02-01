import tcy
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes=True
with open("test2.yaml") as file:
    my_dict = yaml.load(file.read())

# Example 1: Access attribute
result = tcy.access(my_dict, "function_call.60")
print("Example 1:", repr(result))