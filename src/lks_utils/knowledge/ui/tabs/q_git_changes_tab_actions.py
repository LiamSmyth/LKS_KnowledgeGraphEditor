"""Input actions for the knowledge git changes tab."""
from __future__ import annotations

from lks_utils.input import Action, KeyBinding, get_default_bindings

GIT_STAGE_SELECTED = Action(
    id="knowledge.git.stage_selected",
    label="Stage Selected",
    category="Knowledge Git",
    description="Stage the selected changed files.",
    scope="knowledge.git",
)
GIT_STAGE_ALL = Action(
    id="knowledge.git.stage_all",
    label="Stage All",
    category="Knowledge Git",
    description="Stage all current changed files.",
    scope="knowledge.git",
)
GIT_UNSTAGE_SELECTED = Action(
    id="knowledge.git.unstage_selected",
    label="Unstage Selected",
    category="Knowledge Git",
    description="Unstage the selected files.",
    scope="knowledge.git",
)
GIT_UNSTAGE_ALL = Action(
    id="knowledge.git.unstage_all",
    label="Unstage All",
    category="Knowledge Git",
    description="Unstage all currently staged files.",
    scope="knowledge.git",
)
GIT_REVERT_SELECTED = Action(
    id="knowledge.git.revert_selected",
    label="Revert Selected",
    category="Knowledge Git",
    description="Revert the selected files back to HEAD.",
    scope="knowledge.git",
)
GIT_COMMIT_STAGED = Action(
    id="knowledge.git.commit_staged",
    label="Commit Staged",
    category="Knowledge Git",
    description="Commit the currently staged changes.",
    scope="knowledge.git",
)
GIT_COMMIT_ALL = Action(
    id="knowledge.git.commit_all",
    label="Commit All",
    category="Knowledge Git",
    description="Stage and commit all changes.",
    scope="knowledge.git",
)
GIT_LOAD_DIFF = Action(
    id="knowledge.git.load_diff",
    label="Load Diff",
    category="Knowledge Git",
    description="Load the diff for the active selected file.",
    scope="knowledge.git",
)

_bindings = get_default_bindings()
_bindings.register(GIT_STAGE_SELECTED, [KeyBinding("Ctrl+Enter")])
_bindings.register(GIT_STAGE_ALL, [KeyBinding("Ctrl+Alt+Enter")])
_bindings.register(GIT_UNSTAGE_SELECTED, [KeyBinding("Ctrl+Backspace")])
_bindings.register(GIT_UNSTAGE_ALL, [KeyBinding("Ctrl+Alt+Backspace")])
_bindings.register(GIT_REVERT_SELECTED, [KeyBinding("Delete")])
_bindings.register(GIT_COMMIT_STAGED, [KeyBinding("Ctrl+Shift+Enter")])
_bindings.register(GIT_COMMIT_ALL, [KeyBinding("Ctrl+Shift+S")])
_bindings.register(GIT_LOAD_DIFF, [KeyBinding("Ctrl+D")])

__all__ = [
    "GIT_COMMIT_ALL",
    "GIT_COMMIT_STAGED",
    "GIT_LOAD_DIFF",
    "GIT_REVERT_SELECTED",
    "GIT_STAGE_ALL",
    "GIT_STAGE_SELECTED",
    "GIT_UNSTAGE_ALL",
    "GIT_UNSTAGE_SELECTED",
]
