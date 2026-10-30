import logging

from qa_workbench.core.logging import SecretRedactionFilter


def test_secret_redaction_masks_sensitive_values() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "authorization: Bearer-secret token=my-token",
        (),
        None,
    )

    SecretRedactionFilter().filter(record)

    assert record.getMessage() == "authorization=*** token=***"
