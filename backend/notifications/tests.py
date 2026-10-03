from notifications.models import MessageLog
from test_utils import POSTestCase


class NotificationTests(POSTestCase):
    def test_send_test_logs_simulated(self):
        client = self.client_for(self.owner)
        resp = client.post(
            "/api/notifications/send-test/",
            {"to": "03001234567", "message": "hello"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["provider"], "dummy")
        self.assertEqual(data["to"], "923001234567")
        self.assertEqual(MessageLog.objects.count(), 1)
        log = MessageLog.objects.get()
        self.assertEqual(log.status, "simulated")

    def test_cashier_cannot_send_test(self):
        client = self.client_for(self.cashier)
        self.assertEqual(
            client.post("/api/notifications/send-test/", {"to": "03001234567"},
                        format="json").status_code,
            403,
        )

    def test_rules_list(self):
        client = self.client_for(self.owner)
        resp = client.get("/api/notifications/rules/")
        self.assertEqual(resp.status_code, 200)
