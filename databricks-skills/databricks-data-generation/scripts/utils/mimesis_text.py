"""Mimesis integration for generating realistic PII in dbldatagen via PyfuncTextFactory.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.

NOTEBOOK ONLY: This pattern uses PyfuncTextFactory (pandas UDFs) and does NOT work
over Databricks Connect + serverless. For Connect, use values=["James","Mary",...],
random=True for PII columns instead of text=mimesisText(...).
"""

from dbldatagen import PyfuncTextFactory


def _init_mimesis(ctx):
    from mimesis import Generic
    from mimesis.locales import Locale
    ctx.mimesis = Generic(locale=Locale.EN)


MimesisText = (
    PyfuncTextFactory(name="MimesisText")
    .withInit(_init_mimesis)
    .withRootProperty("mimesis")
)


def mimesisText(provider_path: str):
    """Convenience wrapper: mimesisText("person.first_name") -> PyfuncText.

    Args:
        provider_path: Dot-separated path on the Mimesis Generic instance,
            e.g. "person.first_name", "address.city", "person.telephone".
    """
    def gen(g):
        obj = g
        for attr in provider_path.split("."):
            obj = getattr(obj, attr)
        return obj() if callable(obj) else obj
    return MimesisText(gen)
