cdef extern from "a.h":
    int fa();


cpdef int example_b():
    return fa() * 10
