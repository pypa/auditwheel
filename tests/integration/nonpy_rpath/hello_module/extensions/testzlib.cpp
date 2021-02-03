// Copyright 2007 Timo Bingmann <tb@panthema.net>
// Distributed under the Boost Software License, Version 1.0.
// (See http://www.boost.org/LICENSE_1_0.txt)
// Taken from https://panthema.net/2007/0328-ZLibString.html

#include <string.h>
#include <stdexcept>
#include <iostream>
#include <iomanip>
#include <sstream>

#include <zlib.h>
#include "testzlib.h"

/** Compress a STL string using zlib with given compression level and return
  * the binary data. */
std::string compress_string(const std::string& str,
                            int compressionlevel)
{
    z_stream zs;                        // z_stream is zlib's control structure
    memset(&zs, 0, sizeof(zs));

    if (deflateInit(&zs, compressionlevel) != Z_OK)
        throw(std::runtime_error("deflateInit failed while compressing."));

    zs.next_in = (Bytef*)str.data();
    zs.avail_in = str.size();           // set the z_stream's input

    int ret;
    char outbuffer[32768];
    std::string outstring;

    // retrieve the compressed bytes blockwise
    do {
        zs.next_out = reinterpret_cast<Bytef*>(outbuffer);
        zs.avail_out = sizeof(outbuffer);

        ret = deflate(&zs, Z_FINISH);

        if (outstring.size() < zs.total_out) {
            // append the block to the output string
            outstring.append(outbuffer,
                             zs.total_out - outstring.size());
        }
    } while (ret == Z_OK);

    deflateEnd(&zs);

    if (ret != Z_STREAM_END) {          // an error occurred that was not EOF
        std::ostringstream oss;
        oss << "Exception during zlib compression: (" << ret << ") " << zs.msg;
        throw(std::runtime_error(oss.str()));
    }

    return outstring;
}

/** Decompress an STL string using zlib and return the original data. */
std::string decompress_string(const std::string& str)
{
    z_stream zs;                        // z_stream is zlib's control structure
    memset(&zs, 0, sizeof(zs));

    if (inflateInit(&zs) != Z_OK)
        throw(std::runtime_error("inflateInit failed while decompressing."));

    zs.next_in = (Bytef*)str.data();
    zs.avail_in = str.size();

    int ret;
    char outbuffer[32768];
    std::string outstring;

    // get the decompressed bytes blockwise using repeated calls to inflate
    do {
        zs.next_out = reinterpret_cast<Bytef*>(outbuffer);
        zs.avail_out = sizeof(outbuffer);

        ret = inflate(&zs, 0);

        if (outstring.size() < zs.total_out) {
            outstring.append(outbuffer,
                             zs.total_out - outstring.size());
        }

    } while (ret == Z_OK);

    inflateEnd(&zs);

    if (ret != Z_STREAM_END) {          // an error occurred that was not EOF
        std::ostringstream oss;
        oss << "Exception during zlib decompression: (" << ret << ") "
            << zs.msg;
        throw(std::runtime_error(oss.str()));
    }

    return outstring;
}

/** Small dumb tool (de)compressing cin to cout. It holds all input in memory,
  * so don't use it for huge files. */
int main(int argc, char* argv[])
{
    std::string allinput;

    while (std::cin.good())     // read all input from cin
    {
        char inbuffer[32768];
        std::cin.read(inbuffer, sizeof(inbuffer));
        allinput.append(inbuffer, std::cin.gcount());
    }

    if (argc >= 2 && strcmp(argv[1], "-d") == 0)
    {
        std::string cstr = decompress_string( allinput );

        std::cerr << "Inflated data: "
                  << allinput.size() << " -> " << cstr.size()
                  << " (" << std::setprecision(1) << std::fixed
                  << ( ((float)cstr.size() / (float)allinput.size() - 1.0) * 100.0 )
                  << "% increase).\n";

        std::cout << cstr;
    }
    else
    {
        std::string cstr = compress_string( allinput );

        std::cerr << "Deflated data: "
                  << allinput.size() << " -> " << cstr.size()
                  << " (" << std::setprecision(1) << std::fixed
                  << ( (1.0 - (float)cstr.size() / (float)allinput.size()) * 100.0)
                  << "% saved).\n";

        std::cout << cstr;
    }
}
