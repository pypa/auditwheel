# Sample numpy program that requires some BLAS and LAPACK routines to work
# properly
import numpy as np

rng = np.random.RandomState(0)
X = rng.randn(500, 200)
XTX = np.dot(X.T, X)
U, S, VT = np.linalg.svd(XTX)
if all(S > 0):
    print('ok')
else:
    print('[ERROR] invalid singular values:', S)
