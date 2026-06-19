/* =========================================================================
    Unity — Internal Declarations
    ThrowTheSwitch.org
    MIT License

    This file provides the internal definitions needed by unity.c.
    ========================================================================= */

#ifndef UNITY_INTERNALS_H_
#define UNITY_INTERNALS_H_

#include "unity.h"

/* UNITY_LINE_TYPE must be a macro (not a typedef) for unity.c to work.
   unity.c uses "int UNITY_LINE_TYPE line" which with a typedef expands
   to "int int line" (invalid). */
#define UNITY_LINE_TYPE

/* Output macros for printf-based output */
#define UNITY_OUTPUT_CHAR(c)    putchar(c)
#define UNITY_OUTPUT_FLUSH()    fflush(stdout)
#define UNITY_OUTPUT_START()
#define UNITY_OUTPUT_COMPLETE()

/* Internal helper — not part of the public API */
typedef struct UNITY_MEMORY_TAG {
    const char *file;
    int line;
    size_t size;
} UNITY_MEMORY;

#endif /* UNITY_INTERNALS_H_ */
