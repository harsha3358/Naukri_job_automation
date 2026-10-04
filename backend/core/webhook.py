import json
import urllib.request

TIMEOUT_SECONDS = 20
APPS_SCRIPT_PREFIX = "https://script.google.com/macros/s/"


def is_apps_script_link(url: str) -> bool:
    """Only a Google Apps Script web-app link over HTTPS is ever posted to."""
    return url.startswith(APPS_SCRIPT_PREFIX) and url.rstrip("/").endswith("/exec")


def post_json(url: str, payload: dict) -> dict:
    """POST JSON and return the JSON answer.

    Raises OSError when the address cannot be reached, ValueError when the answer is not JSON
    (Google answers with a web page when the script is not shared with "Anyone").
    """
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - callers check the link first
        answer = json.loads(response.read().decode())
    if not isinstance(answer, dict):
        raise ValueError("the answer was not a JSON object")
    return answer
