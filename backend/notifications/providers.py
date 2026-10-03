"""
WhatsApp provider interface.

Provider selection is DB-first: each tenant configures WhatsApp in Settings
(tenants.TenantSettings) — mode ``dummy`` (simulated, safe for testing) or
``meta`` (official WhatsApp Business Cloud API, credentials stored per tenant).

Legacy env-var fallback: if a tenant has no usable DB settings,
WHATSAPP_PROVIDER=meta with WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID still
works exactly as before. The access token is never logged and never returned
in full by any API.

Template support: Meta only delivers business-initiated messages (reminders,
alerts — anything outside the 24h customer-service window) as pre-approved
templates. When a WhatsAppTemplate has ``meta_template_name`` set and the
tenant's provider is Meta, sends go as that template; otherwise free text.
Template mapping: the dispatcher passes the first 3 template variables as
``template_params``; they become the Meta body parameters in order
({{1}}, {{2}}, {{3}}). Meta templates with more than 3 body variables are not
supported yet — keep templates to 3 variables or fewer.
"""
import logging
import os

logger = logging.getLogger(__name__)


def normalize_phone(to: str) -> str:
    """Normalize a phone number to international digits for the WhatsApp API.

    Pakistani numbers: "03001234567" -> "923001234567",
    "+92 300 1234567" -> "923001234567", "923001234567" unchanged.
    Anything else is passed through digit-stripped.
    """
    digits = "".join(ch for ch in str(to) if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        return "92" + digits[1:]
    if len(digits) == 10 and digits.startswith("3"):
        return "92" + digits
    return digits


class BaseProvider:
    name = "base"

    def send(self, to: str, body: str | None = None, template: dict | None = None) -> dict:
        raise NotImplementedError


class DummyProvider(BaseProvider):
    name = "dummy"

    def send(self, to: str, body: str | None = None, template: dict | None = None) -> dict:
        if template:
            logger.info(
                "[whatsapp:dummy] to=%s template=%s params=%s",
                to, template.get("name"), template.get("params"),
            )
        else:
            logger.info("[whatsapp:dummy] to=%s body=%s", to, (body or "")[:120])
        return {"ok": True, "provider": "dummy", "to": to}


class MetaCloudProvider(BaseProvider):
    """Official WhatsApp Business Cloud API (Meta)."""

    name = "meta"
    API_VERSION = "v21.0"

    def __init__(self, phone_number_id: str | None = None, access_token: str | None = None):
        # Explicit DB values win; env vars remain as the legacy fallback.
        self.phone_number_id = phone_number_id or os.environ.get(
            "WHATSAPP_PHONE_NUMBER_ID", ""
        )
        self.token = access_token or os.environ.get("WHATSAPP_TOKEN", "")
        if not self.phone_number_id or not self.token:
            raise RuntimeError(
                "WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_TOKEN must be set for provider=meta"
            )

    def _post(self, payload: dict) -> dict:
        import json
        import urllib.request

        url = (
            f"https://graph.facebook.com/{self.API_VERSION}/"
            f"{self.phone_number_id}/messages"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                # The token lives only in this header; it is never logged and
                # never persisted — only the API reply / error text is stored.
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {
                    "ok": True,
                    "provider": "meta",
                    "response": resp.read().decode()[:500],
                }
        except Exception as e:  # noqa: BLE001 - surfaced in the message log
            return {"ok": False, "provider": "meta", "error": str(e)}

    def send(
        self,
        to: str,
        body: str | None = None,
        template: dict | None = None,
    ) -> dict:
        """Send free text, or a Meta template.

        template = {"name": str, "language": str = "en", "params": [str, ...]}
        """
        to = normalize_phone(to)
        if template:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template["name"],
                    "language": {"code": template.get("language", "en")},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": str(p)}
                                for p in template.get("params", [])
                            ],
                        }
                    ],
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body or ""},
            }
        return self._post(payload)


def get_provider(tenant=None) -> BaseProvider:
    """DB-first provider selection; env vars are the legacy fallback only."""
    if tenant is not None:
        from tenants.models import TenantSettings

        settings = TenantSettings.objects.filter(tenant=tenant).first()
        if settings and settings.whatsapp_mode == TenantSettings.MODE_META:
            if settings.whatsapp_phone_number_id and settings.whatsapp_access_token:
                return MetaCloudProvider(
                    settings.whatsapp_phone_number_id,
                    settings.whatsapp_access_token,
                )
            logger.warning(
                "Tenant %s has WhatsApp mode=meta without credentials; using dummy.",
                tenant.code,
            )
    if os.environ.get("WHATSAPP_PROVIDER", "dummy") == "meta":
        try:
            return MetaCloudProvider()
        except RuntimeError as e:
            logger.warning("Falling back to dummy WhatsApp provider: %s", e)
    return DummyProvider()


def send_whatsapp(
    *,
    tenant,
    to: str,
    body: str,
    event: str,
    template=None,
    template_params: list | None = None,
):
    """Send via the tenant's configured provider and log the attempt.

    ``template`` is a WhatsAppTemplate. When it carries ``meta_template_name``
    and the provider is Meta, the send goes as that approved template with the
    first 3 ``template_params`` as body variables ({{1}}, {{2}}, {{3}});
    otherwise free text is sent. ``to`` is normalized to international digits
    and the normalized value is what gets logged.
    """
    from .models import MessageLog

    provider = get_provider(tenant)
    normalized_to = normalize_phone(to)
    meta_template = None
    if (
        template is not None
        and provider.name == "meta"
        and getattr(template, "meta_template_name", "")
    ):
        meta_template = {
            "name": template.meta_template_name,
            "language": template.meta_language or "en",
            "params": list(template_params or [])[:3],
        }
    result = provider.send(normalized_to, body, template=meta_template)
    if result.get("ok"):
        status = (
            MessageLog.STATUS_SIMULATED
            if result.get("provider") == "dummy"
            else MessageLog.STATUS_SENT
        )
    else:
        status = MessageLog.STATUS_FAILED
    # Never persist secrets: Meta responses don't contain the token, and we
    # only store the API's reply / error text.
    return MessageLog.objects.create(
        tenant=tenant,
        to=normalized_to,
        template=template,
        event=event,
        body=body if not meta_template else f"[template:{meta_template['name']}] {body}",
        status=status,
        provider_response=str(result)[:2000],
    )
