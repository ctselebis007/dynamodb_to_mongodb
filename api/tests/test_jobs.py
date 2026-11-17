import asyncio

import pytest

from app.core.errors import AppError
from app.core.jobs import Job, JobRegistry


async def test_job_progresses_to_done():
    reg = JobRegistry()
    seen: list[int] = []

    async def work(job: Job) -> None:
        for p in range(0, 101, 25):
            job.progress = p
            job.step("s", "Step", status="running", progress=p)
            seen.append(p)
            await asyncio.sleep(0)
        job.step("s", status="done")

    job = reg.start("seed", work)
    done = await reg.wait(job.id)
    assert done.status == "done" and done.progress == 100
    assert seen == [0, 25, 50, 75, 100]
    assert done.steps[0].status == "done"


async def test_failing_job_ends_with_error_code():
    reg = JobRegistry()

    async def work(job: Job) -> None:
        job.step("s", "Step", status="running")
        raise AppError("INDEX_FAILED", "bad", "fix it", 500)

    job = await reg.wait(reg.start("indexes", work).id)
    assert job.status == "error"
    assert job.error is not None and job.error.code == "INDEX_FAILED"
    assert job.steps[0].status == "error"


async def test_second_job_of_same_type_conflicts():
    reg = JobRegistry()
    gate = asyncio.Event()

    async def work(job: Job) -> None:
        await gate.wait()

    first = reg.start("seed", work)
    with pytest.raises(AppError) as e:
        reg.start("seed", work)
    assert e.value.status == 409
    reg.start("indexes", work)
    gate.set()
    await reg.wait(first.id)
