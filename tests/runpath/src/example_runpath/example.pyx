cdef extern from "a.h":
    int fa();


cpdef int example_a():
    return fa()
