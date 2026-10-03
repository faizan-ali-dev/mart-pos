from test_utils import POSTestCase


class CatalogTests(POSTestCase):
    def test_search_products(self):
        client = self.client_for(self.cashier)
        resp = client.get("/api/catalog/products/?search=Test+Tea")
        self.assertEqual(resp.json()["count"], 1)

    def test_barcode_lookup(self):
        self.product.barcode = "8964000999001"
        self.product.save()
        client = self.client_for(self.cashier)
        resp = client.get("/api/catalog/products/?barcode=8964000999001")
        self.assertEqual(resp.json()["count"], 1)

    def test_cashier_cannot_create_product(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/catalog/products/", {"name": "Nope", "retail_price": "10"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_manager_can_create_product(self):
        client = self.client_for(self.manager)
        resp = client.post(
            "/api/catalog/products/",
            {"sku": "T-100", "name": "New Item", "retail_price": "10.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_auto_sku_when_blank(self):
        client = self.client_for(self.manager)
        resp = client.post(
            "/api/catalog/products/",
            {"name": "Sugar 1KG", "retail_price": "150.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.json()["sku"].startswith("SUG-"))

    def test_tenant_isolation(self):
        other = self.client_for(self.other_owner)
        self.assertEqual(other.get("/api/catalog/products/").json()["count"], 0)
        # other tenant can't fetch our product directly either
        self.assertEqual(
            other.get(f"/api/catalog/products/{self.product.id}/").status_code, 404
        )
