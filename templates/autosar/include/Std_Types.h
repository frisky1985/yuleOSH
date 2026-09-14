/**
 * @file Std_Types.h
 * @brief Minimal AUTOSAR standard type definitions (host-test stub).
 *
 * yuleASR BSW platform normally provides this header. This minimal stub lets
 * the autosar template's host tests (unit + system qualification) compile
 * without the full YULEASR_HOME checkout. It mirrors the subset of symbols
 * the config headers and tests reference.
 */

#ifndef STD_TYPES_H
#define STD_TYPES_H

#include <stdint.h>
#include <stdbool.h>

/* ─── Standard integer aliases (AUTOSAR convention) ──────────── */
typedef uint8_t   uint8;
typedef uint16_t  uint16;
typedef uint32_t  uint32;
typedef int8_t    sint8;
typedef int16_t   sint16;
typedef int32_t   sint32;

/* ─── Boolean ────────────────────────────────────────────────── */
typedef bool      boolean;

/* ─── Standard Return Type ───────────────────────────────────── */
typedef uint8     Std_ReturnType;
#define E_OK      0x00U
#define E_NOT_OK  0x01U

/* ─── Standard ON/OFF ────────────────────────────────────────── */
#ifndef STD_ON
#define STD_ON   0x01U
#endif
#ifndef STD_OFF
#define STD_OFF  0x00U
#endif

/* ─── Invalid / null handles ────────────────────────────────── */
#define NULL_PTR ((void *)0)

#endif /* STD_TYPES_H */
