"""Saving API results as ``API`` records (REQ-024, REQ-025, NFR-005).

A result is a fact about a run, so a saved one is sealed like a finalized
execution. Everything in a :class:`FlowResult` is already sanitized by the
runner; this module checks once more and refuses to write anything that still
looks like a credential, instead of trusting a single layer.
"""

from qa_workbench.api.errors import UnsafeToPersistError
from qa_workbench.api.models import Exchange, FlowResult, StepResult
from qa_workbench.core.secrets import find_secrets
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.storage.validation import RecordSchema

STATUSES = frozenset({"passed", "failed", "error"})

API_SCHEMA = RecordSchema(
    prefix="API",
    directory="api-results",
    statuses=STATUSES,
    required=("title", "base_url", "steps"),
    immutable_statuses=STATUSES,
    references={"execution": ("EXEC",)},
)


def _block(text: str) -> str:
    return f"```text\n{text}\n```" if text else "_empty_"


def _exchange_markdown(exchange: Exchange) -> list[str]:
    headers = "\n".join(f"{k}: {v}" for k, v in exchange.request_headers.items())
    response_headers = "\n".join(
        f"{k}: {v}" for k, v in exchange.response_headers.items()
    )
    timing = f"{exchange.elapsed_ms:.0f} ms" if exchange.elapsed_ms is not None else "-"
    return [
        f"**Request** `{exchange.method} {exchange.url}`",
        "",
        _block(headers),
        "",
        _block(exchange.request_body),
        "",
        f"**Response** status {exchange.status if exchange.status is not None else '-'}"
        f" in {timing}",
        "",
        _block(response_headers),
        "",
        _block(exchange.response_body),
    ]


def _step_markdown(number: int, step: StepResult) -> list[str]:
    lines = [f"## {number}. {step.name} - {step.status}", ""]
    if step.error:
        lines += [f"**Could not run:** {step.error}", ""]
    for check in step.checks:
        mark = "pass" if check.passed else "FAIL"
        lines.append(f"- {mark}: {check.name} - {check.detail}")
    if step.checks:
        lines.append("")
    if step.exchange is not None:
        lines += _exchange_markdown(step.exchange) + [""]
    return lines


def render(flow: FlowResult) -> str:
    lines = [f"# {flow.name}", ""]
    for number, step in enumerate(flow.steps, start=1):
        lines += _step_markdown(number, step)
    return "\n".join(lines).rstrip() + "\n"


def save_flow(
    repository: MarkdownRepository,
    flow: FlowResult,
    *,
    execution: str | None = None,
) -> Record:
    """Write ``flow`` as an ``API`` record, or raise without writing anything."""
    body = render(flow)
    leaks = find_secrets(body)
    if leaks:
        raise UnsafeToPersistError(
            f"The result of {flow.name!r} still contains "
            f"{', '.join(sorted(set(leaks)))}; nothing was saved. "
            "Report this as a sanitizer bug."
        )
    fields: dict[str, object] = {
        "status": flow.status,
        "title": flow.name,
        "base_url": flow.base_url,
        "steps": [{"name": s.name, "status": s.status} for s in flow.steps],
    }
    if execution:
        fields["execution"] = execution
    return repository.create("API", fields, body)
