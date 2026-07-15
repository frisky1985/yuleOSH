"""Tests for pipeline/async_runner.py — Async pipeline scheduler."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.pipeline.async_runner import (
    submit_pipeline,
    get_job_status,
    list_jobs,
    get_pipeline_stats,
)


class TestAsyncRunner:
    """Test async pipeline runner."""

    def setup_method(self):
        """Clear jobs before each test."""
        import yuleosh.pipeline.async_runner as ar
        ar._PIPELINE_JOBS.clear()

    def test_submit_and_check(self):
        """Submit pipeline and check job exists."""
        job_id = submit_pipeline("/tmp/test", layer=1)
        assert job_id is not None
        assert len(job_id) > 0

        status = get_job_status(job_id)
        assert status is not None
        assert status["status"] in ("queued", "running", "passed", "failed")

    def test_get_job_status_missing(self):
        """get_job_status for unknown job returns None."""
        status = get_job_status("nonexistent")
        assert status is None

    def test_list_jobs(self):
        """list_jobs returns recent jobs."""
        submit_pipeline("/tmp/test", layer=1)
        jobs = list_jobs(limit=10)
        assert len(jobs) >= 1

    def test_get_pipeline_stats(self):
        """get_pipeline_stats returns counts."""
        stats = get_pipeline_stats()
        assert "total" in stats
        assert "running" in stats
        assert "queued" in stats
        assert "passed" in stats
        assert "failed" in stats

    def test_submit_layer_0(self):
        """Submit layer 0 runs all."""
        job_id = submit_pipeline("/tmp/test", layer=0)
        assert job_id is not None

    def test_list_jobs_empty(self):
        """list_jobs with no jobs."""
        import yuleosh.pipeline.async_runner as ar
        ar._PIPELINE_JOBS.clear()
        jobs = list_jobs()
        assert len(jobs) == 0
