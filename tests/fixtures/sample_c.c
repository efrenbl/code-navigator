#include <stdio.h>
#include <stdlib.h>
#include "local_header.h"

#define MAX_SIZE 100

/* Adds two integers together. */
int simple_function(int a, int b) {
    return helper_function(a) + b;
}

static char *pointer_function(void) {
    return NULL;
}

/* A function prototype. */
int prototype_function(int value);

struct point {
    int x;
    int y;
};

typedef struct point point_t;

typedef unsigned int uint_alias;

enum color {
    RED,
    GREEN,
    BLUE
};

union value {
    int i;
    float f;
};

struct forward_declaration;

int main(int argc, char **argv) {
    struct point p;
    simple_function(1, 2);
    return 0;
}
