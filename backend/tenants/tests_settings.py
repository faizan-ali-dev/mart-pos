"""Tests for per-tenant settings (WhatsApp config + print format)."""
from tenants.models import Tenant, TenantSettings
from test_utils import POSTestCase


class TenantSettingsTests(POSTestCase):
    def test_auto_created_on_tenant_create(self):
        t = Tenant.objects.create(name="Auto Mart", code="AM")
        self.assertTrue(TenantSettings.objects.filter(tenant=t).exists())
        # fixture tenants also got rows via the signal
        self.assertTrue(TenantSettings.objects.filter(tenant=self.tenant).exists())

    def test_owner_get_put(self):
        client = self.client_for(self.owner)
        resp = client.get("/api/tenants/settings/")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["whatsapp_mode"], "dummy")
        self.assertEqual(data["whatsapp_access_token_masked"], "")
        self.assertNotIn("whatsapp_access_token", data)  # write-only, never leaked

        resp = client.put(
            "/api/tenants/settings/",
            {
                "whatsapp_mode": "meta",
                "whatsapp_phone_number_id": "12345",
                "whatsapp_access_token": "tok_abcdef1234",
                "whatsapp_test_mode": True,
                "whatsapp_test_number": "03009998888",
                "default_print_format": "a4",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["whatsapp_access_token_masked"], "****1234")
        self.assertEqual(data["default_print_format"], "a4")
        self.assertNotIn("whatsapp_access_token", data)

    def test_token_preserved_when_omitted(self):
        client = self.client_for(self.owner)
        client.put(
            "/api/tenants/settings/",
            {
                "whatsapp_mode": "meta",
                "whatsapp_phone_number_id": "12345",
                "whatsapp_access_token": "tok_abcdef1234",
            },
            format="json",
        )
        # PUT again without the token — the stored one must survive.
        resp = client.put(
            "/api/tenants/settings/", {"whatsapp_phone_number_id": "99999"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["whatsapp_access_token_masked"], "****1234")
        settings = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings.whatsapp_access_token, "tok_abcdef1234")
        self.assertEqual(settings.whatsapp_phone_number_id, "99999")

    def test_token_preserved_when_empty_string(self):
        client = self.client_for(self.owner)
        client.put(
            "/api/tenants/settings/",
            {
                "whatsapp_mode": "meta",
                "whatsapp_phone_number_id": "12345",
                "whatsapp_access_token": "tok_abcdef1234",
            },
            format="json",
        )
        resp = client.put(
            "/api/tenants/settings/", {"whatsapp_access_token": ""}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        settings = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings.whatsapp_access_token, "tok_abcdef1234")

    def test_meta_mode_requires_credentials(self):
        client = self.client_for(self.owner)
        resp = client.put(
            "/api/tenants/settings/", {"whatsapp_mode": "meta"}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_manager_read_only(self):
        client = self.client_for(self.manager)
        self.assertEqual(client.get("/api/tenants/settings/").status_code, 200)
        resp = client.put(
            "/api/tenants/settings/", {"whatsapp_test_mode": False}, format="json"
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_cashier_forbidden(self):
        client = self.client_for(self.cashier)
        self.assertEqual(client.get("/api/tenants/settings/").status_code, 403)
        self.assertEqual(
            client.put("/api/tenants/settings/", {}, format="json").status_code, 403
        )
