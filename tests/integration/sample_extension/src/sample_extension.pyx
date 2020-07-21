def test_func(x):
    return _test_func(x)

cdef _test_func(x):
    return x + 1