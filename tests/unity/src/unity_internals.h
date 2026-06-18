/* =========================================================================
    Unity — Internal Declarations
    ThrowTheSwitch.org
    MIT License
    ========================================================================= */

#ifndef UNITY_INTERNALS_H_
#define UNITY_INTERNALS_H_

#include "unity.h"

/* Internal helper — not part of the public API */
typedef struct UNITY_MEMORY_TAG {
    const char *file;
    int line;
    size_t size;
} UNITY_MEMORY;

#endif /* UNITY_INTERNALS_H_ */
