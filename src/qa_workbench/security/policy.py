"""Which actions need a person's approval, in each autonomy mode (REQ-030).

Actions have a category. Eight categories are *sensitive*: they always need
approval, in every mode, and no setting turns that off. The modes only decide
what happens to routine work inside the workbench's own data.

* ``assisted``: every action that changes anything asks first.
* ``semi_autonomous``: routine changes to the workbench's own records go ahead;
  sensitive ones ask.
* ``controlled_autonomous``: same approvals as semi-autonomous, and the run is
  bounded by the configured hosts, rate limits, and timeouts (see settings).
"""

from dataclasses import dataclass
from enum import StrEnum


class AutonomyMode(StrEnum):
    ASSISTED = "assisted"
    SEMI_AUTONOMOUS = "semi_autonomous"
    CONTROLLED_AUTONOMOUS = "controlled_autonomous"


DEFAULT_MODE = AutonomyMode.ASSISTED  # the safest, used when nothing is set


class Category(StrEnum):
    READ = "read"
    ROUTINE = "routine"  # changes to the workbench's own records
    DATA_CHANGE = "data_change"  # deleting or altering data outside the workbench
    PRODUCTION_WRITE = "production_write"
    EXTERNAL_COMMENT = "external_comment"  # comments or changes in issues
    INTRUSIVE_TEST = "intrusive_test"
    CODE_CHANGE = "code_change"
    CONFIG_CHANGE = "config_change"
    DESTRUCTIVE_COMMAND = "destructive_command"
    CREDENTIAL_REQUEST = "credential_request"
    OUT_OF_SCOPE = "out_of_scope"


SENSITIVE = frozenset(
    {
        Category.DATA_CHANGE,
        Category.PRODUCTION_WRITE,
        Category.EXTERNAL_COMMENT,
        Category.INTRUSIVE_TEST,
        Category.CODE_CHANGE,
        Category.CONFIG_CHANGE,
        Category.DESTRUCTIVE_COMMAND,
        Category.CREDENTIAL_REQUEST,
        Category.OUT_OF_SCOPE,
    }
)


def requires_approval(mode: AutonomyMode, category: Category) -> bool:
    """Whether ``category`` needs a person's approval in ``mode``."""
    if category is Category.READ:
        return False
    if category in SENSITIVE:
        return True
    return mode is AutonomyMode.ASSISTED  # ROUTINE


@dataclass(frozen=True)
class ActionRequest:
    """What something wants to do. ``detail`` must not contain credentials."""

    action: str
    category: Category
    detail: str = ""
    target_url: str = ""
    requested_by: str = "agent"
