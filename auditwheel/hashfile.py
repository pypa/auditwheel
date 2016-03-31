import hashlib


def hashfile(afile, blocksize=65536):
    """Hash the contents of an open file handle with SHA256"""    
    hasher =  hashlib.sha256()
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()
