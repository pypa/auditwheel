from hello import z_compress, z_uncompress
assert z_uncompress(z_compress('test')) == 'test'
