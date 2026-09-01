"""
composio_bridge.py  —  a thin wrapper around the Composio SDK.

(Named "bridge", not "client", on purpose: Composio's SDK ships its own
internal package called "composio_client", and a local file of that name
would shadow it and break the import.)

Keeps all the "how do I talk to Composio" details in one place so the fetchers
stay readable. Composio manages the OAuth connection and token refresh for
Meta (and Shopify, if that ever moves here too) on their side; this code just
executes a named tool and hands back the payload.

Needs two environment variables:
  COMPOSIO_API_KEY   - from the Composio dashboard
  COMPOSIO_USER_ID   - the user/entity the app connections live under
                       (defaults to "gimi-gimi" if unset; must match what was
                       used when connecting the account in the dashboard)
"""
import os

from utils import PipelineError, log

_client = None


def _as_dict(obj):
    """Composio may return a dict or a small object; normalise to a dict."""
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}


def user_id():
    return os.environ.get("COMPOSIO_USER_ID", "").strip() or "gimi-gimi"


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
    if not api_key:
        raise PipelineError(
            "COMPOSIO_API_KEY is not set. Add it to your .env (local) or to "
            "GitHub -> Settings -> Secrets and variables -> Actions. See "
            "README.md -> 'Composio setup'."
        )
    try:
        from composio import Composio
    except ImportError:
        raise PipelineError(
            "The 'composio' package is not installed. Run "
            "`pip install -r requirements.txt`."
        )
    _client = Composio(api_key=api_key)
    return _client


def execute(slug, arguments):
    """
    Run one Composio tool. Returns the 'data' part of the response, or raises a
    PipelineError with whatever Composio said went wrong.
    """
    client = _get_client()
    try:
        raw = client.tools.execute(slug, arguments=arguments, user_id=user_id())
    except Exception as e:  # noqa: BLE001
        raise PipelineError(
            f"Composio could not run '{slug}': {e}. Check that COMPOSIO_API_KEY "
            f"is valid and that the toolkit is connected (Active) in the "
            f"Composio dashboard for user '{user_id()}'. See TROUBLESHOOTING.md "
            f"-> 'Composio'."
        )
    res = _as_dict(raw)
    ok = res.get("successful", res.get("success", res.get("successfull")))
    if ok is False:
        raise PipelineError(
            f"Composio ran '{slug}' but it failed: {res.get('error') or res}. "
            f"See TROUBLESHOOTING.md -> 'Composio'."
        )
    return res.get("data", res)


def tool_schema(slug):
    """Used by probe_composio.py to print a tool's exact input schema."""
    client = _get_client()
    for call in (
        lambda: client.tools.get(user_id(), tools=[slug]),
        lambda: client.tools.get(user_id=user_id(), tools=[slug]),
        lambda: client.tools.get(slug),
    ):
        try:
            return call()
        except Exception:  # noqa: BLE001
            continue
    raise PipelineError(f"Could not fetch the schema for '{slug}' from Composio.")
