from django.test import TestCase
from rest_framework.authtoken.models import Token

from tenants.models import User
from test_utils import POSTestCase

URL = "/api/tenants/users/"


class AuthTests(POSTestCase):
    def test_login_ok(self):
        resp = self.client.post(
            "/api/auth/login/", {"username": "t_cashier", "password": "pw123"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "cashier")
        self.assertEqual(data["user"]["tenant_name"], "Test Mart")

    def test_login_wrong_password(self):
        resp = self.client.post(
            "/api/auth/login/", {"username": "t_cashier", "password": "nope"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_me(self):
        client = self.client_for(self.owner)
        resp = client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "t_owner")

    def test_unauthenticated_blocked(self):
        resp = self.client.get("/api/catalog/products/")
        self.assertEqual(resp.status_code, 401)


class UserManagementTests(POSTestCase):
    def test_owner_creates_cashier(self):
        client = self.client_for(self.owner)
        resp = client.post(URL, {
            "username": "new_cashier", "password": "secret123",
            "first_name": "New", "role": "cashier",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        user = User.objects.get(username="new_cashier")
        self.assertEqual(user.tenant, self.tenant)
        self.assertTrue(user.check_password("secret123"))
        # password must not leak in the response
        self.assertNotIn("password", resp.json())
        # and the new user can log in
        login = self.client.post(
            "/api/auth/login/", {"username": "new_cashier", "password": "secret123"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

    def test_owner_creates_manager(self):
        client = self.client_for(self.owner)
        resp = client.post(URL, {
            "username": "new_manager", "password": "secret123", "role": "manager",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_manager_creates_cashier_ok(self):
        client = self.client_for(self.manager)
        resp = client.post(URL, {
            "username": "mgr_cashier", "password": "secret123", "role": "cashier",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_manager_cannot_create_manager(self):
        client = self.client_for(self.manager)
        resp = client.post(URL, {
            "username": "sneaky", "password": "secret123", "role": "manager",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_manager_cannot_create_owner(self):
        client = self.client_for(self.manager)
        resp = client.post(URL, {
            "username": "sneaky2", "password": "secret123", "role": "owner",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_cashier_list_forbidden(self):
        client = self.client_for(self.cashier)
        self.assertEqual(client.get(URL).status_code, 403)

    def test_cashier_create_forbidden(self):
        client = self.client_for(self.cashier)
        resp = client.post(URL, {"username": "x", "password": "secret123"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_owner_lists_tenant_users_only(self):
        client = self.client_for(self.owner)
        usernames = [u["username"] for u in client.get(URL).json()["results"]]
        self.assertIn("t_owner", usernames)
        self.assertIn("t_cashier", usernames)
        self.assertNotIn("o_owner", usernames)

    def test_manager_lists_cashiers_only(self):
        client = self.client_for(self.manager)
        usernames = [u["username"] for u in client.get(URL).json()["results"]]
        self.assertIn("t_cashier", usernames)
        self.assertNotIn("t_owner", usernames)
        self.assertNotIn("t_manager", usernames)

    def test_owner_deactivates_cashier_then_login_fails(self):
        client = self.client_for(self.owner)
        resp = client.patch(f"{URL}{self.cashier.id}/", {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertFalse(self.cashier.is_active)
        login = self.client.post(
            "/api/auth/login/", {"username": "t_cashier", "password": "pw123"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 400)
        # deactivated token is rejected too
        stale = self.client_for(self.cashier)
        self.assertEqual(stale.get("/api/auth/me/").status_code, 401)

    def test_owner_cannot_deactivate_self(self):
        client = self.client_for(self.owner)
        resp = client.patch(f"{URL}{self.owner.id}/", {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_manager_cannot_touch_owner(self):
        client = self.client_for(self.manager)
        # object-level denial surfaces as 404 (not found in manager's scope)
        resp = client.patch(f"{URL}{self.owner.id}/", {"first_name": "Hacked"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_manager_cannot_promote_cashier(self):
        client = self.client_for(self.manager)
        resp = client.patch(
            f"{URL}{self.cashier.id}/", {"role": "manager"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_resets_password(self):
        client = self.client_for(self.owner)
        resp = client.post(
            f"{URL}{self.cashier.id}/reset-password/", {"password": "brandnew"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        login = self.client.post(
            "/api/auth/login/", {"username": "t_cashier", "password": "brandnew"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

    def test_manager_resets_cashier_password_ok(self):
        client = self.client_for(self.manager)
        resp = client.post(
            f"{URL}{self.cashier.id}/reset-password/", {"password": "brandnew"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_delete_disabled(self):
        client = self.client_for(self.owner)
        self.assertEqual(client.delete(f"{URL}{self.cashier.id}/").status_code, 405)

    def test_create_requires_password(self):
        client = self.client_for(self.owner)
        resp = client.post(URL, {"username": "nopw", "role": "cashier"}, format="json")
        self.assertEqual(resp.status_code, 400)
