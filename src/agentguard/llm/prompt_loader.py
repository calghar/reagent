import logging
from functools import cache
from pathlib import Path

import jinja2

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "data" / "prompts"


@cache
def _get_env() -> jinja2.Environment:
    """Return a cached Jinja2 Environment pointed at the prompts directory.

    Returns:
        Configured :class:`jinja2.Environment` instance.
    """
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,  # noqa: S701  # nosec B701
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_prompt(template_name: str, **kwargs: object) -> str:
    """Render a prompt template by name with the given context variables.

    Args:
        template_name: Filename of the ``.j2`` template under
            ``src/agentguard/data/prompts/``.
        **kwargs: Template context variables passed to the renderer.

    Returns:
        Rendered prompt string.

    Raises:
        jinja2.TemplateNotFound: If *template_name* does not exist.
    """
    env = _get_env()
    template = env.get_template(template_name)
    return str(template.render(**kwargs))
