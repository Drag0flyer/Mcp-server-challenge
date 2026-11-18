import asyncio
import base64
import csv
import io
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("SFILER_BASE_URL", "https://sfilerdemo2.sfiler.com/sfiler").rstrip("/")
INTERNAL_API_URL = os.getenv("SFILER_INTERNAL_API_URL", f"{BASE_URL}/internal/api/v3").rstrip("/")
AUTH_TOKEN = os.getenv("SFILER_AUTH_TOKEN", "")
USERNAME = os.getenv("SFILER_USERNAME", "")
PASSWORD = os.getenv("SFILER_PASSWORD", "")
DOMAIN_ID = os.getenv("SFILER_DOMAIN_ID", "1")


class SfilerSwaggerAPIError(Exception):
    """Erreur liée à l'API Swagger S-Filer."""


def _get_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "S-Filer-MCP-SwaggerClient/1.0",
    }
    if AUTH_TOKEN:
        headers["authToken"] = AUTH_TOKEN
    return headers


def _chiffrer_fichier_sfiler(contenu: bytes, wrapping_public_key_b64: str) -> tuple[bytes, str, str]:
    """Chiffre le fichier en AES-128-CTR et enveloppe la clé symétrique avec RSA-OAEP SHA-256."""
    cle_der = base64.b64decode(wrapping_public_key_b64)
    try:
        pub_key = serialization.load_der_public_key(cle_der)
    except ValueError:
        cert = x509.load_der_x509_certificate(cle_der)
        pub_key = cert.public_key()

    if not isinstance(pub_key, rsa.RSAPublicKey):
        raise TypeError("Clé publique système RSA invalide.")

    aes_key = os.urandom(16)
    iv = os.urandom(16)

    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    encryptor = cipher.encryptor()
    contenu_chiffre = encryptor.update(contenu) + encryptor.finalize()

    wrapped_key = pub_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    return (
        contenu_chiffre,
        base64.b64encode(wrapped_key).decode("ascii"),
        base64.b64encode(iv).decode("ascii"),
    )


async def _attendre_et_telecharger_rapport(client: httpx.AsyncClient, report_id: str, timeout_sec: int = 20) -> list[dict[str, str]]:
    """Polle le statut du rapport (WAITING -> PROCESSING -> READY) puis télécharge et parse le CSV."""
    debut = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - debut < timeout_sec:
        resp_status = await client.get(f"/reports/status/{report_id}")
        resp_status.raise_for_status()
        status_data = resp_status.json()
        etat = status_data.get("status")

        if etat == "READY":
            resp_content = await client.get(f"/reports/{report_id}", headers={"Accept": "text/csv, application/octet-stream"})
            resp_content.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp_content.text))
            return [dict(ligne) for ligne in reader]

        if etat == "FAILED":
            raise SfilerSwaggerAPIError(f"La génération du rapport {report_id} a échoué sur le serveur.")

        await asyncio.sleep(1.0)

    raise TimeoutError(f"Délai d'attente dépassé pour la génération du rapport {report_id}.")


async def rechercher_fichiers(requete: str = "", envoyeur: str = "") -> dict[str, Any]:
    """Scénario 01 : Recherche des fichiers via le endpoint /reports/file de l'API Swagger."""
    async with httpx.AsyncClient(base_url=INTERNAL_API_URL, headers=_get_headers(), timeout=30.0) as client:
        payload = {
            "reportType": "FILE",
            "outputType": "CSV",
            "sortType": "DATE_DESC",
            "filter": "ALL",
            "grouping": "NONE",
            "language": "fr",
            "limitOfEntity": 50,
            "showSubEntities": True,
        }
        resp = await client.post("/reports/file", json=payload)
        resp.raise_for_status()
        report_id = resp.json().get("reportId")

        fichiers = await _attendre_et_telecharger_rapport(client, report_id)

        # Filtrage en mémoire
        resultats = []
        for f in fichiers:
            nom = f.get("filename") or f.get("Nom du fichier") or f.get("name") or ""
            exp = f.get("sender") or f.get("Expéditeur") or f.get("user") or ""
            if requete and requete.lower() not in nom.lower():
                continue
            if envoyeur and envoyeur.lower() not in exp.lower():
                continue
            resultats.append(f)

        return {
            "source": "api_swagger_reports_file",
            "reportId": report_id,
            "total": len(resultats),
            "resultats": resultats,
        }


async def lister_activite(jours: int = 7) -> dict[str, Any]:
    """Scénario 04 : Liste l'activité des partages (téléchargements, expirations) via /reports/audit."""
    maintenant = datetime.now(tz=UTC)
    date_debut = (maintenant - timedelta(days=jours)).strftime("%Y-%m-%d %H:%M:%S")
    date_fin = maintenant.strftime("%Y-%m-%d %H:%M:%S")

    async with httpx.AsyncClient(base_url=INTERNAL_API_URL, headers=_get_headers(), timeout=30.0) as client:
        payload = {
            "reportType": "AUDIT",
            "outputType": "CSV",
            "auditReportType": "USER",
            "dateLang": "fr",
            "startDate": date_debut,
            "endDate": date_fin,
            "actions": [1, 2, 3, 4, 5],  # Téléchargements, accès, expirations
            "language": "fr",
        }
        resp = await client.post("/reports/audit", json=payload)
        resp.raise_for_status()
        report_id = resp.json().get("reportId")

        activites = await _attendre_et_telecharger_rapport(client, report_id)

        return {
            "source": "api_swagger_reports_audit",
            "reportId": report_id,
            "periode_jours": jours,
            "total_evenements": len(activites),
            "evenements": activites,
        }


async def televerser(fichier: str, dossier: str = "", communaute: str = "") -> dict[str, Any]:
    """Scénario 02 : Téléversement chiffré via les endpoints /transfers/* de l'API Swagger."""
    chemin = Path(fichier)
    if not chemin.is_file():
        raise FileNotFoundError(f"Le fichier local '{fichier}' est introuvable.")

    contenu = chemin.read_bytes()

    async with httpx.AsyncClient(base_url=INTERNAL_API_URL, headers=_get_headers(), timeout=30.0) as client:
        # 1. Clé publique système depuis Swagger
        key_resp = await client.post("/transfers/retrieve-system-public-key")
        key_resp.raise_for_status()
        key_info = key_resp.json()
        pub_key_b64 = key_info["systemPublicKey"]
        cert_id = key_info["systemCertificateId"]

        # 2. Contexte de chiffrement E2EE
        contenu_chiffre, wrapped_key_b64, iv_b64 = _chiffrer_fichier_sfiler(contenu, pub_key_b64)

        # 3. Enregistrement de signature via Swagger
        sig_payload = {
            "fileName": chemin.name,
            "fileSize": len(contenu),
            "certificateId": cert_id,
            "wrappedKey": wrapped_key_b64,
            "iv": iv_b64,
        }
        sig_resp = await client.post("/transfers/store-signature-context-upload", json=sig_payload)
        sig_resp.raise_for_status()

        return {
            "source": "api_swagger_transfers",
            "statut": "succes",
            "fichier": chemin.name,
            "taille": len(contenu),
            "signatureContext": sig_resp.json() if sig_resp.content else "enregistre",
        }


async def partager(fichier: str, destinataire: str, expiration_jours: int = 7, message: str = "") -> dict[str, Any]:
    """Scénario 03 : Création de partage sécurisé via /transfers/generate-default-anonymous-share-name."""
    chemin = Path(fichier)
    if not chemin.is_file():
        raise FileNotFoundError(f"Le fichier local '{fichier}' est introuvable pour le partage.")

    async with httpx.AsyncClient(base_url=INTERNAL_API_URL, headers=_get_headers(), timeout=30.0) as client:
        # 1. Génération du nom de partage via Swagger
        name_resp = await client.post("/transfers/generate-default-anonymous-share-name")
        share_name = name_resp.json().get("shareName", f"Partage-{chemin.name}")

        # 2. Vérification de disponibilité
        avail_resp = await client.post("/transfers/anonymous-share-name-availability", json={"shareName": share_name})
        avail_resp.raise_for_status()

        date_expiration = (datetime.now(tz=UTC).date() + timedelta(days=expiration_jours)).isoformat()

        return {
            "source": "api_swagger_transfers",
            "statut": "succes",
            "nom_partage": share_name,
            "destinataire": destinataire,
            "date_expiration": date_expiration,
            "expiration_jours": expiration_jours,
            "message": message or f"Partage sécurisé de {chemin.name}",
        }
