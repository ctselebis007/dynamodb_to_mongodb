"""In-memory background jobs (seed, indexes). Lost on API restart/reload."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.core.errors import AppError, to_app_error
from app.core.models import ApiModel

log = logging.getLogger("demokit.jobs")

JobStatus = Literal["running", "done", "error"]
StepStatus = Literal["pending", "running", "done", "error"]


class JobStep(ApiModel):
    id: str
    label: str
    status: StepStatus = "pending"
    detail: str = ""
    progress: int = 0


class JobError(ApiModel):
    code: str
    message: str
    hint: str = ""


class Job(ApiModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: str
    status: JobStatus = "running"
    progress: int = 0
    steps: list[JobStep] = []
    error: JobError | None = None

    def step(self, id: str, label: str | None = None, **changes) -> JobStep:
        for s in self.steps:
            if s.id == id:
                break
        else:
            s = JobStep(id=id, label=label or id)
            self.steps.append(s)
        if label:
            s.label = label
        for k, v in changes.items():
            setattr(s, k, v)
        return s


JobFn = Callable[[Job], Awaitable[None]]


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, type: str, fn: JobFn) -> Job:
        if any(j.type == type and j.status == "running" for j in self._jobs.values()):
            raise AppError(
                "JOB_RUNNING", f"A {type} job is already running.", "Wait for it to finish.", 409
            )
        job = Job(type=type)
        self._jobs[job.id] = job
        self._tasks[job.id] = asyncio.create_task(self._run(job, fn))
        return job

    async def _run(self, job: Job, fn: JobFn) -> None:
        try:
            await fn(job)
            job.status, job.progress = "done", 100
        except Exception as exc:
            err = to_app_error(exc)
            if err.code == "INTERNAL":
                log.exception("%s job failed", job.type)
            job.status = "error"
            job.error = JobError(code=err.code, message=err.message, hint=err.hint)
            for s in job.steps:
                if s.status == "running":
                    s.status = "error"
        finally:
            self._tasks.pop(job.id, None)

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", "The API may have restarted.", 404)
        return job

    async def wait(self, job_id: str) -> Job:
        task = self._tasks.get(job_id)
        if task:
            await task
        return self.get(job_id)


jobs = JobRegistry()
router = APIRouter(prefix="/api/setup/jobs", tags=["setup"])


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    return jobs.get(job_id)
