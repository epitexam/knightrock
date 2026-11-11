"""The state names other systems ask about, in one place.

The physics, the combat resolver and the renderer ask an entity whether it is
dashing, flying in knockback or dizzy. They ask through the predicates on
:class:`~src.entities.entity.Entity`, which compare against these names, so a
renamed state is one edit here and not a string search across the codebase.
"""

from typing import Final

DASH: Final[str] = "dash"
KNOCKBACK: Final[str] = "knockback"
STAGGER: Final[str] = "stagger"
DIZZY: Final[str] = "dizzy"
