cdef extern from "b.h":
    int fb();


cpdef int example_b():
    return fb()
