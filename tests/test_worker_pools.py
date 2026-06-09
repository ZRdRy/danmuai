"""S-014: dedicated AI thread pool."""

from app.worker_pools import ai_worker_pool


def test_ai_worker_pool_isolated_with_max_two_threads():
    pool = ai_worker_pool()
    assert pool.maxThreadCount() == 2
    assert pool is ai_worker_pool()
