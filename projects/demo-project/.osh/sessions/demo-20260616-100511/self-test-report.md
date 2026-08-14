# Self-Test Report: demo-20260616-100511

## Test Runner
- **Runner**: pytest
- **Total Tests**: 2
- **Passed**: 2
- **Failed**: 0
- **Status**: ✅

## Test Summary
```
2 passed in 0.03s
```

## Test Output
```
..
WARNING: Failed to generate report: No data to report.


ERROR: Coverage failure: total of 0 is less than fail-under=80
                                                                         [100%]
================================ tests coverage ================================
FAIL Required test coverage of 80% not reached. Total coverage: 0.00%
2 passed in 0.03s

/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/coverage/inorout.py:561: CoverageWarning: Module src/yuleosh was never imported. (module-not-imported); see https://coverage.readthedocs.io/en/7.14.1/messages.html#warning-module-not-imported
  self.warn(f"Module {pkg} was never imported.", slug="module-not-imported")
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/coverage/control.py:958: CoverageWarning: No data was collected. (no-data-collected); see https://coverage.readthedocs.io/en/7.14.1/messages.html#warning-no-data-collected
  self._warn("No data was collected.", slug="no-data-collected")
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/pytest_cov/plugin.py:366: CovReportWarning: Failed to generate report: No data to report.

  warnings.warn(CovReportWarning(message), stacklevel=1)

```

## Spec Scenarios (0)

## Coverage Note
Run CI Layer 1 to generate detailed coverage metrics for compliance.
