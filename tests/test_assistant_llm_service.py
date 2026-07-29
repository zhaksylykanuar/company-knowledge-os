from __future__ import annotations

import json

import httpx
import pytest

from app.services.assistant_llm_service import (
    OPENAI_RESPONSES_URL,
    AssistantEvidenceFact,
    AssistantLLMRejectedError,
    AssistantLLMUnavailableError,
    generate_assistant_reasoning,
)


FACT = AssistantEvidenceFact(
    id="priority.summary",
    text="Главный ход: проверить безопасный релиз.",
    citation_ids=("evidence_ref:priority",),
)


def _response_payload(reasoning: dict) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(reasoning, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


def _reasoning(*, fact_text: str = FACT.text, fact_id: str = FACT.id) -> dict:
    return {
        "fact": {"text": fact_text, "fact_ids": [fact_id]},
        "interpretation": {
            "text": "Релиз требует отдельной проверки перед решением.",
            "fact_ids": [fact_id],
        },
        "objection": {
            "text": "Одного факта недостаточно для оценки всех рисков.",
            "fact_ids": [fact_id],
        },
        "recommendation": {
            "text": "Открыть подтверждённую задачу и проверить основания.",
            "fact_ids": [fact_id],
        },
    }


async def test_responses_request_is_non_persistent_strict_and_evidence_bound() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_response_payload(_reasoning()))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await generate_assistant_reasoning(
            api_key="test-openai-key",
            model="gpt-5.6",
            reasoning_effort="medium",
            max_output_tokens=1_200,
            timeout_seconds=10,
            safety_identifier="privacy-safe-id",
            query="Что сейчас главное?",
            facts=[FACT],
            client=client,
        )

    assert captured["url"] == OPENAI_RESPONSES_URL
    assert captured["authorization"] == "Bearer test-openai-key"
    payload = captured["payload"]
    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "medium", "context": "current_turn"}
    assert payload["safety_identifier"] == "privacy-safe-id"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    user_context = json.loads(payload["input"][1]["content"])
    assert user_context == {
        "question": "Что сейчас главное?",
        "retrieved_facts": [{"id": FACT.id, "text": FACT.text}],
    }
    assert result.fact.text == FACT.text
    assert result.fact.citation_ids == ("evidence_ref:priority",)
    assert result.recommendation.citation_ids == ("evidence_ref:priority",)


@pytest.mark.parametrize(
    "reasoning",
    [
        _reasoning(fact_id="unknown.fact"),
        _reasoning(fact_text="Придуманный факт."),
        {
            **_reasoning(),
            "recommendation": {
                "text": "Неподтверждённая рекомендация.",
                "fact_ids": [],
            },
        },
    ],
)
async def test_evidence_critic_rejects_unsupported_output(reasoning: dict) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response_payload(reasoning))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AssistantLLMRejectedError):
            await generate_assistant_reasoning(
                api_key="test-openai-key",
                model="gpt-5.6",
                reasoning_effort="medium",
                max_output_tokens=1_200,
                timeout_seconds=10,
                safety_identifier="privacy-safe-id",
                query="Что сейчас главное?",
                facts=[FACT],
                client=client,
            )


@pytest.mark.parametrize(
    "provider_body",
    [
        {"status": "incomplete", "output": []},
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "not available"}],
                }
            ],
        },
    ],
)
async def test_incomplete_or_refused_response_fails_without_provider_text(
    provider_body: dict,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AssistantLLMUnavailableError) as error:
            await generate_assistant_reasoning(
                api_key="private-key-must-not-surface",
                model="gpt-5.6",
                reasoning_effort="medium",
                max_output_tokens=1_200,
                timeout_seconds=10,
                safety_identifier="privacy-safe-id",
                query="Что сейчас главное?",
                facts=[FACT],
                client=client,
            )

    assert "private-key-must-not-surface" not in str(error.value)
    assert "not available" not in str(error.value)
