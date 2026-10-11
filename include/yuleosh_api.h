/**
 * yuleOSH API Interface Definitions (SWE.2.BP2)
 *
 * Defines external interfaces for the yuleOSH compliance platform.
 * All interfaces include data types and value ranges.
 */

#ifndef YULEOSH_API_H
#define YULEOSH_API_H

/* ── Compliance Check Request ─────────────────────────────────── */

/**
 * @brief Compliance check request structure
 * @interface IF-001: API → ComplianceChecker
 */
typedef struct {
    char project_dir[512];      /* Project root directory path */
    char profile_names[8][64];  /* Profile names (max 8, each ≤64 chars) */
    int  profile_count;         /* Number of profiles (1-8) */
    char output_format[16];     /* "markdown" | "json" */
} ComplianceCheckRequest;

/**
 * @brief Compliance check response structure
 * @interface IF-002: ComplianceChecker → API
 */
typedef struct {
    int  total_bps;             /* Total base practices (≥0) */
    int  passed;                /* Passed BPs (0 ≤ passed ≤ total_bps) */
    int  partial;               /* Partial BPs (0 ≤ partial ≤ total_bps) */
    int  failed;                /* Failed BPs (0 ≤ failed ≤ total_bps) */
    char standard[32];          /* Standard name, e.g. "ASPICE" */
    char version[16];           /* Version string, e.g. "3.1" */
    char generated_at[64];      /* ISO 8601 timestamp */
} ComplianceCheckResponse;

/* ── Evidence Pack Request ────────────────────────────────────── */

/**
 * @brief Evidence pack request
 * @interface IF-005: Test Executor → Evidence
 */
typedef struct {
    char project_dir[512];
    char commit_hash[40];       /* Git commit SHA-1 */
    char evidence_dir[512];     /* Output directory for evidence */
} EvidencePackRequest;

/* ── Status Codes ─────────────────────────────────────────────── */

#define YULEOSH_OK              0   /* Success */
#define YULEOSH_ERR_NOT_FOUND   1   /* Project directory not found */
#define YULEOSH_ERR_PROFILE     2   /* Profile not found or invalid */
#define YULEOSH_ERR_PARSE       3   /* Parse error in project files */
#define YULEOSH_ERR_EVIDENCE    4   /* Evidence generation failed */

#endif /* YULEOSH_API_H */
