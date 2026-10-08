from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.research_context import (
    build_research_overview_context,
    build_research_sample_context,
)
from tests.research_base import RESEARCH_SAMPLES, ResearchApiTestCase

CHAT = "/api/research-copilot/chat"
MS_TOKEN = re.compile(r"\bMs\b")


class _LlmOff:
    """Force the offline path regardless of any key in a developer's .env."""

    def __enter__(self):
        self._patches = [
            patch("routers.research_copilot.llm_available", return_value=False),
            patch("routers.agent.llm_available", return_value=False),
            patch("routers.ai.llm_available", return_value=False),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class PhysicsCopilotRouteCompatibilityTests(ResearchApiTestCase):
    def test_existing_agent_and_ai_routes_still_require_authentication(self) -> None:
        for method, path, body in (
            ("GET", "/api/agent/status", None),
            ("POST", "/api/agent/chat", {"message": "hello"}),
            ("GET", "/api/ai/status", None),
            ("POST", "/api/ai/copilot", {"question": "hello"}),
        ):
            with self.subTest(path=path):
                response = self.anonymous.request(method, path, json=body)
                self.assertEqual(response.status_code, 401)

    def test_existing_agent_routes_work_with_a_vite_issued_token(self) -> None:
        with _LlmOff():
            status = self.client_a.get("/api/agent/status")
            self.assertEqual(status.status_code, 200, status.text)
            self.assertIn("llmAvailable", status.json())

            chat = self.client_a.post(
                "/api/agent/chat", json={"message": "What should I try next?", "history": []}
            )
            self.assertEqual(chat.status_code, 200, chat.text)
            self.assertIn("answer", chat.json())

            ai = self.client_a.get("/api/ai/status")
            self.assertEqual(ai.status_code, 200, ai.text)

    def test_research_copilot_status_requires_auth(self) -> None:
        self.assertEqual(self.anonymous.get("/api/research-copilot/status").status_code, 401)
        with _LlmOff():
            ok = self.client_a.get("/api/research-copilot/status")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["researchContext"])


class ResearchCopilotGroundingTests(ResearchApiTestCase):
    def _sample_with_both(self, client=None, name="Copilot sample") -> dict:
        sample = self.create_sample(client, name=name)
        self.assertEqual(self.upload_magnetometry(sample["id"], client).status_code, 201)
        self.assertEqual(self.upload_xrd(sample["id"], client).status_code, 201)
        return sample

    def test_offline_answer_reads_back_stored_values_only(self) -> None:
        sample = self._sample_with_both()
        with _LlmOff():
            response = self.client_a.post(CHAT, json={"message": "Summarize", "sample_id": sample["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        answer = payload["answer"]

        self.assertEqual(payload["source"], "stored-records")
        self.assertTrue(payload["researchContext"])
        self.assertIn("Copilot sample", answer)
        self.assertIn("Hc(-)", answer)
        self.assertIn("-107.5", answer)  # stored Hc(-) = -107.452 Oe, 4 significant digits
        self.assertIn("125.8", answer)
        self.assertIn("saturation evidence = high", answer)
        self.assertIn("instrument_metadata", answer)
        self.assertIn("Candidate intensity maxima", answer)
        self.assertIn("NOT a saturation magnetization", answer)

    def test_context_never_uses_ms_label_or_unsupported_inference(self) -> None:
        sample = self._sample_with_both()
        with _LlmOff():
            answer = self.client_a.post(
                CHAT, json={"message": "What is Ms?", "sample_id": sample["id"]}
            ).json()["answer"]
        self.assertIsNone(MS_TOKEN.search(answer), "legacy Ms label leaked into Copilot output")
        for forbidden in ("Scherrer", "MnAl", "tau-", "lattice parameter", "squareness"):
            self.assertNotIn(forbidden, answer)

    def test_llm_receives_stored_context_and_guardrails(self) -> None:
        sample = self._sample_with_both(name="LLM grounded sample")
        mock_chat = AsyncMock(return_value=("Grounded reply.", "gemini"))
        with (
            patch("routers.research_copilot.llm_available", return_value=True),
            patch("routers.research_copilot.chat_completion", mock_chat),
        ):
            response = self.client_a.post(
                CHAT,
                json={
                    "message": "What is the coercivity?",
                    "sample_id": sample["id"],
                    "history": [{"role": "user", "content": "hi"}],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answer"], "Grounded reply.")
        self.assertEqual(response.json()["source"], "gemini")

        system, user_message = mock_chat.call_args.args[:2]
        self.assertIn("LLM grounded sample", user_message)
        self.assertIn("Hc(-)", user_message)
        self.assertIn("What is the coercivity?", user_message)
        self.assertIn("NOT a saturation magnetization", user_message)
        self.assertIn("Never describe the largest measured moment as saturation", system)
        self.assertIn("do not assign phases", system)

    def test_llm_failure_falls_back_to_stored_records(self) -> None:
        sample = self._sample_with_both(name="Fallback sample")
        mock_chat = AsyncMock(return_value=("Text generation is off", "heuristic"))
        with (
            patch("routers.research_copilot.llm_available", return_value=True),
            patch("routers.research_copilot.chat_completion", mock_chat),
        ):
            payload = self.client_a.post(
                CHAT, json={"message": "Summarize", "sample_id": sample["id"]}
            ).json()
        self.assertEqual(payload["source"], "stored-records")
        self.assertIn("Fallback sample", payload["answer"])

    def test_user_b_cannot_ground_chat_on_user_a_sample(self) -> None:
        sample = self._sample_with_both(name="A confidential sample")
        with _LlmOff():
            response = self.client_b.post(CHAT, json={"message": "Tell me", "sample_id": sample["id"]})
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("A confidential sample", response.text)

    def test_overview_contains_only_callers_samples(self) -> None:
        self.create_sample(self.client_a, name="Overview A only")
        self.create_sample(self.client_b, name="Overview B only")
        captured = AsyncMock(return_value=("ok", "gemini"))
        with (
            patch("routers.research_copilot.llm_available", return_value=True),
            patch("routers.research_copilot.chat_completion", captured),
        ):
            self.client_b.post(CHAT, json={"message": "What samples do I have?"})
        user_message = captured.call_args.args[1]
        self.assertIn("Overview B only", user_message)
        self.assertNotIn("Overview A only", user_message)

    def test_general_chat_without_sample_works_offline(self) -> None:
        with _LlmOff():
            response = self.client_a.post(CHAT, json={"message": "How do I measure Hc?"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["sampleId"])

    def test_unknown_sample_returns_404(self) -> None:
        with _LlmOff():
            response = self.client_a.post(
                CHAT, json={"message": "x", "sample_id": "00000000-0000-0000-0000-000000000000"}
            )
        self.assertEqual(response.status_code, 404)

    def test_sample_listing_unaffected_by_chat(self) -> None:
        listed = self.client_a.get(RESEARCH_SAMPLES)
        self.assertEqual(listed.status_code, 200)


class ResearchContextUnitTests(ResearchApiTestCase):
    def _sample(self):
        return SimpleNamespace(name="S", formula=None, notes=None, id="s1")

    def test_missing_analysis_fields_do_not_crash_or_invent_values(self) -> None:
        experiment = SimpleNamespace(
            experiment_type="magnetometry",
            original_filename="partial.dat",
            analysis_version="1",
            uploaded_at="2026-10-01",
            user_confirmed_mass_mg=None,
            analysis_json={
                "summary": {"mh_segment_count": 1},
                "mh_analyses": [
                    {
                        "segment_index": 0,
                        "analysis": {
                            "hysteresis": {"Hc_negative_Oe": None},
                            "high_field": {},
                            "normalized": {"available": False, "reason": "mass_unresolved"},
                        },
                    }
                ],
            },
        )
        text = build_research_sample_context(self._sample(), [experiment])
        self.assertIn("not available", text)
        self.assertIn("mass_unresolved", text)
        self.assertNotIn("None emu/g", text)
        self.assertIsNone(MS_TOKEN.search(text))

    def test_empty_sample_and_overview(self) -> None:
        text = build_research_sample_context(self._sample(), [])
        self.assertIn("No experiments have been saved", text)
        self.assertIn("no saved research Samples", build_research_overview_context([], {}))

    def test_unknown_experiment_type_is_reported_without_values(self) -> None:
        experiment = SimpleNamespace(
            experiment_type="vsm-legacy",
            original_filename="x.dat",
            analysis_version="1",
            uploaded_at="t",
            user_confirmed_mass_mg=None,
            analysis_json={},
        )
        self.assertIn("no summary available", build_research_sample_context(self._sample(), [experiment]))
