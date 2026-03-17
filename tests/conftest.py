"""
Shared pytest fixtures and configuration.
"""

import asyncio
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring full system")
    config.addinivalue_line("markers", "security: security audit tests")
    config.addinivalue_line("markers", "slow: tests that take >5 seconds")


@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
