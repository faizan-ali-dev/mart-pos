"""
WhatsApp provider interface.

The sending backend is swappable: set WHATSAPP_PROVIDER=meta with
WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID for the official Meta Cloud API,
otherwise the DummyProvider is used (logs every send as 'simulated' — safe
for dev and tests, no real messages ever leave the machine).
"""
import logging
import os

logger = logging.getLogger(__name__)


class BaseProvider:
    name = "base"

    def send(self, to: str, body: str) -> dict:
        raise NotImplementedError


class DummyProvider(BaseProvider):
    name = "dummy"

    def send(self, to: str, body: str) -> dict:
        logger.info("[whatsapp:dummy] to=%s body=%s", to, body[:120])
        return {"ok": True, "provider": "dummy", "to": to}


class MetaCloudProvider(BaseProvider):
    """Official WhatsApp Business Cloud API (Meta)."""

    name = "meta"

    def __init__(self):
        self.token = os.environ.get("WHATSAPP_TOKEN", "")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        if not self.token or not self.phone_number_id:
            raise RuntimeError(
                "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be set for provider=meta"
            )

    def send(self, to: str, body: str) -> dict:
        import json
        import urllib.request

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        payload = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body},
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"ok": True, "provider": "meta", "response": resp.read().decode()[:500]}
        except Exception as e:  # noqa: BLE001 - surfaced in the message log
            return {"ok": False, "provider": "meta", "error": str(e)}


def get_provider() -> BaseProvider:
    if os.environ.get("WHATSAPP_PROVIDER", "dummy") == "meta":
        try:
            return MetaCloudProvider()
        except RuntimeError as e:
            logger.warning("Falling back to dummy WhatsApp provider: %s", e)
    return DummyProvider()


def send_whatsapp(*, tenant, to: str, body: str, event: str, template=None):
    """Send via the configured provider and log the attempt."""
    from .models import MessageLog

    provider = get_provider()
    result = provider.send(to, body)
    if result.get("ok"):
        status = (
            MessageLog.STATUS_SIMULATED
            if result.get("provider") == "dummy"
            else MessageLog.STATUS_SENT
        )
    else:
        status = MessageLog.STATUS_FAILED
    return MessageLog.objects.create(
        tenant=tenant,
        to=to,
        template=template,
        event=event,
        body=body,
        status=status,
        provider_response=str(result)[:2000],
    )
