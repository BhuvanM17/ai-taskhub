import httpx
import pytest

from app.providers import run_remote


def test_retries_transient_response():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"summary":"ok"}'}}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = run_remote("summarize", "hello", client=client, sleep=lambda _: None)
    assert result["summary"] == "ok"
    assert len(calls) == 3


def test_permanent_failure_is_not_retried():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(401)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_remote("extract", "hello", client=client, sleep=lambda _: None)
    assert len(calls) == 1


def test_rejects_invalid_model_output():
    def handle(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"wrong":true}'}}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError):
            run_remote("summarize", "hello", client=client, sleep=lambda _: None)
