/**
 * yuleOSH Pipeline Interface Definitions (SWE.2.BP2)
 *
 * Defines interfaces between Pipeline components and Step Handlers.
 */

#ifndef YULEOSH_PIPELINE_H
#define YULEOSH_PIPELINE_H

/* ── Pipeline Context ─────────────────────────────────────────── */

/**
 * @brief Pipeline execution context passed between steps
 * @interface IF-003: Pipeline → Step Handlers
 */
typedef struct {
    char project_dir[512];      /* Project root directory */
    char spec_path[512];        /* Input spec file path */
    char profile_names[8][64];  /* Active compliance profiles */
    int  profile_count;         /* Number of active profiles */
    int  current_step;          /* Current step index (0-based) */
    int  total_steps;           /* Total steps in pipeline */
} PipelineContext;

/**
 * @brief Step execution result
 * @interface IF-003: Step Handlers → Pipeline
 */
typedef struct {
    int  step_id;               /* Step identifier */
    char step_name[64];         /* Step name, e.g. "sys_requirements" */
    int  status;                /* 0=success, non-zero=error */
    char output_path[512];      /* Generated output file path */
    char message[256];          /* Human-readable status message */
} StepResult;

/* ── Test Task ────────────────────────────────────────────────── */

/**
 * @brief Test execution task specification
 * @interface IF-004: Pipeline → Test Executor
 */
typedef struct {
    char test_type[16];         /* "unit" | "integration" | "sil" | "hil" */
    char target_arch[32];       /* "arm-none-eabi" | "riscv64" | "host" */
    char source_dir[512];       /* Source directory to compile */
    char output_dir[512];       /* Output directory for results */
    int  timeout_seconds;       /* Execution timeout (30-3600) */
} TestTask;

/**
 * @brief Test execution result
 * @interface IF-005: Test Executor → Evidence
 */
typedef struct {
    char report_path[512];      /* Result JSON file path */
    int  all_passed;            /* 1=all tests passed, 0=any failed */
    int  total_cases;           /* Total test cases (≥0) */
    int  passed_cases;          /* Passed cases (0 ≤ passed ≤ total) */
    int  failed_cases;          /* Failed cases (0 ≤ failed ≤ total) */
    char environment[64];       /* "SIL" | "HIL" | "host" */
} TestResult;

#endif /* YULEOSH_PIPELINE_H */
