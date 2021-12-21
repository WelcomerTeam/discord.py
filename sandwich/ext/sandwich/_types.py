from typing import Any, Callable, TypeVar


FuncT = TypeVar('FuncT', bound=Callable[..., Any])
