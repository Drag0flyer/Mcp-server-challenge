# S-Filer MCP Server — Approche Idéale Swagger REST API

Cette branche (`swagger-rest-api`) implémente la solution du **Défi Étudiant S-Filer 2026 (OKIOK)** en utilisant exclusivement l'API REST décrite par le fichier Swagger [swagger-server-internal-v3-api.yaml](file:///home/minixx/Documents/travailplus/uni/projet-perso-pour-cv/okiokdefi/swagger-server-internal-v3-api.yaml).

---

## 1. Principes de cette approche

Contrairement à la branche principale (`main`) qui s'appuie sur la reproduction des requêtes Web / AJAX du portail S-Filer :
- **Zéro scraping HTML** : Aucun parsing de formulaire ou de fragment de page JSP/Struts.
- **Utilisation des rapports asynchrones du Swagger** :
  - **Scénario 01 (Retrouver)** : utilise `POST /internal/api/v3/reports/file` (schéma `FileReportInfo` avec sortie `CSV`), attend que le rapport soit prêt (`GET /reports/status/{id}`), puis extrait les fichiers au format CSV structuré.
  - **Scénario 04 (Rendre compte)** : utilise `POST /internal/api/v3/reports/audit` (schéma `AuditReportInfo`), télécharge les événements au format CSV (téléchargements, accès, expirations).
- **Gestion des transferts et de la cryptographie via le Swagger** :
  - **Scénario 02 (Téléverser)** : utilise `POST /transfers/retrieve-system-public-key` et `POST /transfers/store-signature-context-upload`.
  - **Scénario 03 (Partager)** : utilise `POST /transfers/generate-default-anonymous-share-name` et `POST /transfers/anonymous-share-name-availability`.
- **Intégration FastMCP OpenAPIProvider** :
  - FastMCP charge directement la spécification `swagger-server-internal-v3-api.yaml` pour exposer automatiquement les 45 routes sous forme d'outils MCP complémentaires.

---

## 2. Comparatif des deux approches

| Critère | Branche `main` (Approche Web/AJAX) | Branche `swagger-rest-api` (Approche Swagger REST) |
| :--- | :--- | :--- |
| **Source de données** | Requêtes Web (`RecentFilesAjax.action`, `/ajaxupload`) | Spécification Swagger (`/internal/api/v3/*`) |
| **Format de retour brut** | Fragment HTML Struts2 (analysé par parseur) | Fichiers de rapports CSV structurés |
| **Authentification requise** | Identifiants Web (`SFILER_USERNAME` + `SFILER_PASSWORD`) | Jeton d'API dans l'en-tête HTTP (`authToken: <token>`) |
| **Conformité stricte au sujet** | Solution pragmatique contournant les limites d'accès REST | Conforme à 100% à la règle *"uniquement le Swagger fourni"* |

---

## 3. Configuration et Démarrage

### Configuration (`.env`)
```env
SFILER_BASE_URL=https://sfilerdemo2.sfiler.com/sfiler
SFILER_INTERNAL_API_URL=https://sfilerdemo2.sfiler.com/sfiler/internal/api/v3
SFILER_AUTH_TOKEN=votre_jeton_d_acces_direct_ici
```

### Lancement du serveur MCP Swagger
```bash
uv run python -m okiokdefi.server_swagger
```

### Exécution des tests unitaires
```bash
uv run python -m unittest discover tests
```
