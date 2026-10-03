"""DeepEval worker. Run in the isolated evaluation environment (no Django).

Offline metrics are deliberately labelled deterministic proxies. The optional
LLM mode executes DeepEval's semantic RAG metrics with a configured Groq judge.
No results are substituted when the judge or framework fails.
"""
import contextlib
import importlib.metadata
import io
import json
import os
import re
import sys

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_NO_INSPECT_PROMPT", "1")
from deepeval import evaluate
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


class BenchmarkMetric(BaseMetric):
    def __init__(self, metric):
        self.metric = metric
        self.threshold = .5
        self.async_mode = False
        self.evaluation_model = "deterministic gold-location/token checks"

    def measure(self, test_case, *args, **kwargs):
        data = test_case.metadata
        if self.metric == "faithfulness":
            claims = data.get("claims", [])
            support = " ".join(test_case.retrieval_context or []).casefold()
            checked = [" ".join(c.get("quote", "").split()).casefold() in " ".join(support.split()) for c in claims if c.get("quote")]
            self.score = sum(checked) / len(checked) if checked else 0
            self.reason = f"{sum(checked)}/{len(checked)} claimed supporting quotes occur in retrieved context. This does not verify paraphrase entailment."
        elif self.metric == "answer_relevancy":
            terms = set(data.get("required_concepts", []))
            supported = sum(term.casefold() in test_case.actual_output.casefold() for term in terms)
            self.score = supported / len(terms) if terms else 0
            self.reason = f"Answer covers {supported}/{len(terms)} team-labelled reference concepts; lexical proxy, not a semantic judge."
        else:
            gold = set(data["gold_locations"])
            retrieved = data["retrieved_locations"]
            if self.metric == "context_precision":
                relevant = [location in gold for location in retrieved]
                # Average precision rewards relevant material earlier in ranking.
                precisions = [sum(relevant[:i + 1]) / (i + 1) for i, value in enumerate(relevant) if value]
                self.score = sum(precisions) / sum(relevant) if any(relevant) else 0
                self.reason = f"Gold-location average precision over {len(retrieved)} retrieved content units."
            else:
                self.score = len(gold & set(retrieved)) / len(gold) if gold else 0
                self.reason = f"Retrieved {len(gold & set(retrieved))}/{len(gold)} required source locations."
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case, *args, **kwargs)

    @property
    def __name__(self):
        return self.metric


def semantic_metrics(model_name):
    from deepeval.models import DeepEvalBaseLLM
    from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric
    from groq import Groq
    class GroqJudge(DeepEvalBaseLLM):
        def __init__(self):
            self.model_name = model_name
            self.client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=60, max_retries=1)
        def load_model(self):
            return self.client
        def generate(self, prompt, schema=None):
            result = self.client.chat.completions.create(model=self.model_name, temperature=0,
                messages=[{"role": "user", "content": prompt + ("\nReturn only valid JSON matching this schema: " + json.dumps(schema.model_json_schema()) if schema else "")}],
                response_format={"type": "json_object"} if schema else None, max_completion_tokens=5000)
            text = result.choices[0].message.content
            return schema.model_validate_json(text) if schema else text
        async def a_generate(self, prompt, schema=None):
            return self.generate(prompt, schema)
        def get_model_name(self):
            return self.model_name
    judge = GroqJudge()
    return [cls(model=judge, async_mode=False) for cls in (FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric)]


def main():
    payload = json.load(sys.stdin)
    rows = [row for row in payload["cases"] if row["supported"]]
    cases = [LLMTestCase(name=row["id"], input=row["question"], actual_output=row["answer"], expected_output=row["reference_answer"],
        context=row["gold_contexts"], retrieval_context=row["contexts"], metadata=row) for row in rows]
    mode = payload.get("mode", "deterministic")
    if mode == "llm":
        if not payload.get("judge_model") or not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("LLM evaluation requires a judge model and GROQ_API_KEY in the evaluation worker.")
        metrics = semantic_metrics(payload["judge_model"])
    else:
        metrics = [BenchmarkMetric(name) for name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")]
    with contextlib.redirect_stdout(io.StringIO()):
        result = evaluate(cases, metrics, async_config=AsyncConfig(run_async=False),
            cache_config=CacheConfig(write_cache=False, use_cache=False),
            display_config=DisplayConfig(show_indicator=False, print_results=False, inspect_after_run=False))
    results = [{"id": row.name, "metrics": [{"name": metric.name, "score": metric.score, "reason": metric.reason, "error": metric.error} for metric in row.metrics_data]} for row in result.test_results]
    aggregates = {}
    for row in results:
        for metric in row["metrics"]:
            if metric["score"] is not None and not metric["error"]:
                aggregates.setdefault(metric["name"], []).append(metric["score"])
    print("LABTWIN_RESULT=" + json.dumps({"framework": "DeepEval", "framework_version": importlib.metadata.version("deepeval"),
        "mode": mode, "metric_interpretation": "semantic LLM-judge metrics" if mode == "llm" else "deterministic proxy metrics; see per-case reasons",
        "metrics": {name: sum(values) / len(values) for name, values in aggregates.items()}, "cases": results,
        "judge_model": payload.get("judge_model") if mode == "llm" else None}))


if __name__ == "__main__":
    main()
