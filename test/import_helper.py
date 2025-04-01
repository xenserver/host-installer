"""helpers for unit-testing functions in scripts without permanent global mocks"""
import sys
from contextlib import contextmanager
from types import ModuleType

from typing import Generator
from mock import Mock


@contextmanager
def mocked_modules(*module_names: str) -> Generator[None, None, None]:
    """Context manager that temporarily mocks the specified modules.

    :param module_names: Variable number of names of the modules to be mocked.
    :yields: None

    During the context, the specified modules are added to the sys.modules
    dictionary as instances of the ModuleType class.
    This effectively mocks the modules, allowing them to be imported and used
    within the context. After the context, the mocked modules are removed
    from the sys.modules dictionary.

    Example usage:
    ```python
    with mocked_modules("module1", "module2"):
        # Code that uses the mocked modules
    ```
    """
    for module_name in module_names:
        sys.modules[module_name] = Mock()
    yield
    for module_name in module_names:
        sys.modules.pop(module_name)

def create_mock_module(name, attributes=None):
    """
    Create a mock module with the given name and attributes.
    :param name: Name of the module.
    :param attributes: Dictionary of attributes to add to the module.
    :return: Mocked module.
    """
    mock_module = ModuleType(name)
    if attributes:
        for attr_name, attr_value in attributes.items():
            setattr(mock_module, attr_name, attr_value)
    return mock_module
