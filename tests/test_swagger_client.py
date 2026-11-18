import unittest
from unittest.mock import AsyncMock, patch

import httpx

from okiokdefi import server_swagger, swagger_client


class TestSwaggerClient(unittest.IsolatedAsyncioTestCase):
    async def test_rechercher_fichiers_swagger_csv(self):
        fake_csv = "filename,sender,date,size\ncontrat.pdf,bob@exemple.com,2026-11-18,1024\nautre.txt,alice@exemple.com,2026-11-17,50\n"

        async def fake_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/reports/file"):
                return httpx.Response(200, json={"reportId": "rep-123"})
            elif url.endswith("/reports/status/rep-123"):
                return httpx.Response(200, json={"status": "READY"})
            elif url.endswith("/reports/rep-123"):
                return httpx.Response(200, text=fake_csv)
            return httpx.Response(404)

        transport = httpx.MockTransport(fake_handler)
        with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport, base_url="http://test/internal/api/v3")):
            res = await swagger_client.rechercher_fichiers(requete="contrat")
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["resultats"][0]["filename"], "contrat.pdf")
            self.assertEqual(res["resultats"][0]["sender"], "bob@exemple.com")

    async def test_lister_activite_swagger_audit(self):
        fake_csv = "event,user,fileName,action,date\nDOWNLOAD,user1,hi.txt,TELECHARGEMENT,2026-11-18\nEXPIRED,user2,test.pdf,EXPIRATION,2026-11-17\n"

        async def fake_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/reports/audit"):
                return httpx.Response(200, json={"reportId": "audit-456"})
            elif url.endswith("/reports/status/audit-456"):
                return httpx.Response(200, json={"status": "READY"})
            elif url.endswith("/reports/audit-456"):
                return httpx.Response(200, text=fake_csv)
            return httpx.Response(404)

        transport = httpx.MockTransport(fake_handler)
        with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport, base_url="http://test/internal/api/v3")):
            res = await swagger_client.lister_activite(jours=7)
            self.assertEqual(res["total_evenements"], 2)
            self.assertEqual(res["evenements"][0]["event"], "DOWNLOAD")
            self.assertEqual(res["evenements"][1]["action"], "EXPIRATION")

    async def test_partager_swagger_endpoints(self):
        async def fake_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/transfers/generate-default-anonymous-share-name"):
                return httpx.Response(200, json={"shareName": "Partage-Auto-2026"})
            elif url.endswith("/transfers/anonymous-share-name-availability"):
                return httpx.Response(200, json={"available": True})
            return httpx.Response(404)

        transport = httpx.MockTransport(fake_handler)
        with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport, base_url="http://test/internal/api/v3")):
            res = await swagger_client.partager("test_mcp.txt", "partenaire@exemple.com", 5)
            self.assertEqual(res["statut"], "succes")
            self.assertEqual(res["nom_partage"], "Partage-Auto-2026")
            self.assertEqual(res["destinataire"], "partenaire@exemple.com")
            self.assertEqual(res["expiration_jours"], 5)

    async def test_server_swagger_tool_call(self):
        fake_result = {
            "source": "api_swagger_reports_file",
            "reportId": "rep-789",
            "total": 1,
            "resultats": [{"filename": "rapport.csv", "sender": "me@domain.com"}],
        }
        with patch("okiokdefi.swagger_client.rechercher_fichiers", new=AsyncMock(return_value=fake_result)):
            res = await server_swagger.rechercher_fichiers("rapport")
            self.assertIn("<untrusted_data>", res)
            self.assertIn("rapport.csv", res)
            self.assertIn("[RAPPEL SÉCURITÉ", res)


if __name__ == "__main__":
    unittest.main()
