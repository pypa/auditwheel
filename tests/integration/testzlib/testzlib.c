#include <zlib.h>
#include <stdlib.h>
#include <Python.h>


static PyObject *
run(PyObject *self, PyObject *args)
{
    int res;

    (void)self;
    (void)args;

#if defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 24)
    res = gzflags() != 0;
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 17)
    /* blacklist ineffective on manylinux 2014 */
    res = 0;
#elif defined(__GLIBC_PREREQ)
    {
        void* memory = zcalloc(NULL, 1U, 1U);
        res = (memory != NULL);
        zcfree(NULL, memory);
    }
#else
    res = 0;
#endif
    return PyLong_FromLong(res);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testzlib(void)
{
    static PyMethodDef module_methods[] = {
        {"run", (PyCFunction)run, METH_NOARGS, "run."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "testzlib",
        "testzlib module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
