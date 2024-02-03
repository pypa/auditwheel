/* A simple example program to square a number using no shared libraries. */

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    int x;

    if (argc != 2)
    {
        fputs("Expected exactly one command line argument\n", stderr);
        return EXIT_FAILURE;
    }

    x = atoi(argv[1]);
    printf("%d\n", x*x);
    return EXIT_SUCCESS;
}
