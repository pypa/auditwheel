if __name__ == "__main__":
    from hello import z_compress, z_uncompress

    assert z_uncompress(z_compress("test")) == "test"
