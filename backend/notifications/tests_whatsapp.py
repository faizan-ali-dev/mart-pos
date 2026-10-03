"""Tests for WhatsApp provider selection, templates, phone normalization, send-test."""
import json
import os
from unittest.mock import patch

from notifications.models import MessageLog, WhatsAppTemplate
from notifications.providers import (
    DummyProvider,
    MetaCloudProvider,
    get_provider,
    normalize_phone,
    send_whatsapp,
)
from tenants.models import TenantSettings
from test_utils import POSTestCase


class FakeHTTPResponse:
    def __init__(self, body=b'{"messages": [{"id": "wamid.1"}]}'):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PhoneNormalizationTests(POSTestCase):
    def test_pakistani_formats(self):
        self.assertEqual(normalize_phone("03001234567"), "923001234567")
        self.assertEqual(normalize_phone("+92 300 1234567"), "923001234567")
        self.assertEqual(normalize_phone("923001234567"), "923001234567")
        self.assertEqual(normalize_phone("3001234567"), "923001234567")
        self.assertEqual(normalize_phone("+92-300-1234567"), "923001234567")


class ProviderSelectionTests(POSTestCase):
    def _enable_meta(self):
        s, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        s.whatsapp_mode = "meta"
        s.whatsapp_phone_number_id = "PN123"
        s.whatsapp_access_token = "tok_secret9999"
        s.whatsapp_test_mode = False
        s.save()
        return s

    def test_default_is_dummy(self):
        self.assertIsInstance(get_provider(self.tenant), DummyProvider)

    def test_meta_from_db_settings(self):
        self._enable_meta()
        provider = get_provider(self.tenant)
        self.assertIsInstance(provider, MetaCloudProvider)
        self.assertEqual(provider.phone_number_id, "PN123")
        # the DB token (not env) is used
        self.assertEqual(provider.token, "tok_secret9999")

    def test_meta_without_credentials_falls_back_to_dummy(self):
        s, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        s.whatsapp_mode = "meta"  # no credentials stored
        s.save()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHATSAPP_PROVIDER", None)
            self.assertIsInstance(get_provider(self.tenant), DummyProvider)


class MetaTemplateTests(POSTestCase):
    def test_template_payload_shape(self):
        provider = MetaCloudProvider("PN123", "tok_secret")
        with patch(
            "urllib.request.urlopen",
            return_value=FakeHTTPResponse(),
        ) as mock_urlopen:
            result = provider.send(
                "03001234567",
                "hello",
                template={"name": "bill_receipt", "language": "ur",
                          "params": ["DM-1", "500"]},
            )
        self.assertTrue(result["ok"])
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode())
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["to"], "923001234567")
        self.assertEqual(payload["template"]["name"], "bill_receipt")
        self.assertEqual(payload["template"]["language"]["code"], "ur")
        params = payload["template"]["components"][0]["parameters"]
        self.assertEqual([p["text"] for p in params], ["DM-1", "500"])
        # the token never appears in the returned result
        self.assertNotIn("tok_secret", str(result))

    def test_dispatch_uses_meta_template_when_set(self):
        s, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        s.whatsapp_mode = "meta"
        s.whatsapp_phone_number_id = "PN123"
        s.whatsapp_access_token = "tok_secret9999"
        s.save()
        tpl = WhatsAppTemplate.objects.create(
            tenant=self.tenant,
            name="bill_receipt",
            language="en",
            body="Bill {bill_no} total {total}",
            meta_template_name="bill_receipt",
            meta_language="en",
        )
        with patch.object(
            MetaCloudProvider, "send", return_value={"ok": True, "provider": "meta"}
        ) as mock_send:
            log = send_whatsapp(
                tenant=self.tenant,
                to="03001234567",
                body="Bill DM-1 total 500",
                event="bill_completed",
                template=tpl,
                template_params=["DM-1", "500"],
            )
        sent_template = mock_send.call_args.kwargs["template"]
        self.assertEqual(sent_template["name"], "bill_receipt")
        self.assertEqual(sent_template["params"], ["DM-1", "500"])
        self.assertEqual(log.status, MessageLog.STATUS_SENT)
        self.assertEqual(log.to, "923001234567")

    def test_dispatch_text_fallback_without_meta_name(self):
        s, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        s.whatsapp_mode = "meta"
        s.whatsapp_phone_number_id = "PN123"
        s.whatsapp_access_token = "tok_secret9999"
        s.save()
        tpl = WhatsAppTemplate.objects.create(
            tenant=self.tenant, name="plain", language="en", body="hi"
        )
        with patch.object(
            MetaCloudProvider, "send", return_value={"ok": True, "provider": "meta"}
        ) as mock_send:
            send_whatsapp(
                tenant=self.tenant, to="03001234567", body="hi",
                event="x", template=tpl,
            )
        self.assertIsNone(mock_send.call_args.kwargs["template"])

    def test_dummy_provider_ignores_template(self):
        log = send_whatsapp(
            tenant=self.tenant, to="03001234567", body="hi", event="x",
            template_params=["a"],
        )
        self.assertEqual(log.status, MessageLog.STATUS_SIMULATED)


class SendTestViewTests(POSTestCase):
    def _settings(self):
        s, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        return s

    def test_forces_test_number_in_test_mode(self):
        s = self._settings()
        s.whatsapp_test_mode = True
        s.whatsapp_test_number = "03009998888"
        s.save()
        client = self.client_for(self.owner)
        resp = client.post(
            "/api/notifications/send-test/",
            {"to": "03001112222", "message": "hi"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["provider"], "dummy")
        self.assertEqual(data["to"], "923009998888")
        self.assertTrue(data["forced_to_test_number"])
        log = MessageLog.objects.get(id=data["log_id"])
        self.assertEqual(log.to, "923009998888")

    def test_no_forcing_when_test_mode_off(self):
        s = self._settings()
        s.whatsapp_test_mode = False
        s.save()
        client = self.client_for(self.owner)
        resp = client.post(
            "/api/notifications/send-test/",
            {"to": "03001112222", "message": "hi"},
            format="json",
        )
        data = resp.json()
        self.assertFalse(data["forced_to_test_number"])
        self.assertEqual(data["to"], "923001112222")

    def test_meta_without_credentials_400(self):
        s = self._settings()
        s.whatsapp_mode = "meta"
        s.whatsapp_phone_number_id = ""
        s.whatsapp_access_token = ""
        s.save()
        client = self.client_for(self.owner)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHATSAPP_PROVIDER", None)
            os.environ.pop("WHATSAPP_TOKEN", None)
            os.environ.pop("WHATSAPP_PHONE_NUMBER_ID", None)
            resp = client.post(
                "/api/notifications/send-test/", {"to": "03001112222"}, format="json"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("token", resp.json()["detail"].lower())
