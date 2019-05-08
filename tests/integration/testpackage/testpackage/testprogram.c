/* A simple example program to square a number using GSL. */

#include <gsl/gsl_math.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    double x;
    char *startptr, *endptr;

    if (argc != 2)
    {
        fputs("Expected exactly one command line argument\n", stderr);
        return EXIT_FAILURE;
    }

    startptr = argv[1];
    endptr = NULL;
    x = strtod(startptr, &endptr);

    if (startptr == endptr)
    {
        fputs("Expected command line argument to be a float\n", stderr);
        return EXIT_FAILURE;
    }
    
    x = gsl_pow_2(x);
    printf("%g\n", x);
    return EXIT_SUCCESS;
}
