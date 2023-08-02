import warnings

def deprecated(func):
    def new_func(*args, **kwargs):
        warnings.warn(f"Call to deprecated function {func.__name__}.", category=DeprecationWarning, stacklevel=2)
        return func(*args, **kwargs)
    return new_func