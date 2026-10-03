# Stadtbibliothek – Ausleih-API

Eine schlanke, vollständige REST-API für die Ausleihe einer kleinen
Stadtbibliothek. Sie verwaltet **Bücher** (Titel, Autor, eindeutige ISBN,
Erscheinungsjahr, Exemplaranzahl), **Mitglieder** (Name, eindeutige E-Mail,
Mitglied seit) und **Ausleihen** (Buch, Mitglied, Ausleihdatum, Fälligkeit
14 Tage später, Rückgabedatum) und erzwingt die drei Ausleihregeln: höchstens
drei offene Ausleihen je Mitglied, Ausleihe nur solange ein Exemplar frei ist,
und die Rückgabe schließt die Ausleihe.

Alle schreibenden Endpunkte sind per `X-API-Key`-Header geschützt, alle Fehler
haben dieselbe Antwortform `{"error": {"code", "message", "details"}}`, und die
OpenAPI-Dokumentation ist unter `/docs` verfügbar.

## Tech-Stack

- **Sprache:** Python 3.12
- **Framework:** FastAPI
- **Validierung:** Pydantic v2
- **ORM:** SQLAlchemy 2.0 (`DeclarativeBase`, `Mapped`/`mapped_column`)
- **Datenbank:** SQLite
- **Server:** Uvicorn
- **Tests:** pytest + FastAPI `TestClient` (httpx)
- **Qualität:** ruff, mypy

## Installation

```bash
py -m pip install -r requirements.txt
```

## Starten (Entwicklung)

Der Dienst startet **ohne jede Vorkonfiguration**. Wird kein `LIBRARY_API_KEY`
gesetzt, erzeugt die Anwendung beim Start einen zufälligen Schlüssel, legt ihn in
der Laufzeitdatei `library_api_key.local` ab und protokolliert den Pfad. Die
SQLite-Datenbank und ihr Schema werden beim Start automatisch angelegt.

```bash
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Danach sind erreichbar:

- Health-Check: <http://localhost:8000/health>
- OpenAPI-Dokumentation (Swagger UI): <http://localhost:8000/docs>

### API-Key explizit setzen

Für eine feste Konfiguration (z. B. in der Produktion) den Schlüssel vor dem
Start exportieren:

```bash
# Windows (cmd)
set LIBRARY_API_KEY=mein-geheimer-schluessel

# Windows (PowerShell)
$env:LIBRARY_API_KEY = "mein-geheimer-schluessel"

# Linux / macOS
export LIBRARY_API_KEY=mein-geheimer-schluessel

py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Umgebungsvariablen

| Variable | Bedeutung | Standard |
| --- | --- | --- |
| `LIBRARY_DATABASE_URL` | SQLAlchemy-Datenbank-URL | `sqlite:///./library.db` |
| `LIBRARY_API_KEY` | Schlüssel für schreibende Endpunkte (`X-API-Key`) | beim Start generiert und in `library_api_key.local` gespeichert |
| `LIBRARY_API_KEY_FILE` | Pfad der Laufzeitdatei für den generierten Schlüssel | `library_api_key.local` |

## Bedienung

Alle Fehlerantworten haben dieselbe Form:

```json
{"error": {"code": "not_found", "message": "...", "details": null}}
```

Mögliche `code`-Werte: `unauthorized`, `not_found`, `validation_error`,
`duplicate_isbn`, `duplicate_email`, `book_has_open_loans`,
`loan_limit_reached`, `no_copy_available`, `loan_already_returned`.

Schreibende Anfragen (`POST`, `PUT`, `PATCH`, `DELETE`) benötigen den Header
`X-API-Key`. Lesende Anfragen sind öffentlich.

### Endpunkte

| Methode | Pfad | Beschreibung | Body | Antwort |
| --- | --- | --- | --- | --- |
| `POST` | `/books` | Buch anlegen | `BookCreate` | `201 BookRead` / `409` doppelte ISBN / `422` |
| `GET` | `/books?q=&limit=&offset=` | Bücher suchen und blättern (`q` = Teilstring in Titel oder Autor, ohne Groß-/Kleinschreibung) | – | `200 BookPage` |
| `GET` | `/books/{id}` | Ein Buch lesen | – | `200 BookRead` / `404` |
| `PUT`/`PATCH` | `/books/{id}` | Buch ändern | `BookUpdate` | `200 BookRead` / `404` / `409` |
| `DELETE` | `/books/{id}` | Buch löschen | – | `204` / `404` / `409` bei offenen Ausleihen |
| `POST` | `/members` | Mitglied anlegen | `MemberCreate` | `201 MemberRead` / `409` doppelte E-Mail |
| `GET` | `/members?limit=&offset=` | Mitglieder blättern | – | `200 MemberPage` |
| `GET` | `/members/{id}` | Ein Mitglied lesen | – | `200 MemberRead` / `404` |
| `PUT`/`PATCH` | `/members/{id}` | Mitglied ändern | `MemberUpdate` | `200 MemberRead` / `404` / `409` |
| `DELETE` | `/members/{id}` | Mitglied löschen | – | `204` / `404` |
| `POST` | `/loans` | Ausleihe anlegen | `LoanCreate` | `201 LoanRead` / `404` unbekanntes Buch/Mitglied / `409` Limit oder Verfügbarkeit |
| `GET` | `/loans?member_id=&book_id=&status=open|returned&limit=&offset=` | Ausleihen filtern und blättern | – | `200 LoanPage` |
| `GET` | `/loans/{id}` | Eine Ausleihe lesen | – | `200 LoanRead` / `404` |
| `GET` | `/loans/overdue?limit=&offset=` | Offene Ausleihen mit `due_at` vor heute | – | `200 LoanPage` |
| `POST` | `/loans/{id}/return` | Ausleihe zurückgeben | – | `200 LoanRead` / `404` / `409` bereits zurückgegeben |
| `GET` | `/health` | Health-Check inkl. Datenbankprüfung | – | `200 {"status": "ok"}` |

### Schemas

**`BookCreate` / `BookUpdate`**

```json
{
  "title": "Der Process",
  "author": "Franz Kafka",
  "isbn": "978-3-518-18818-3",
  "publication_year": 1925,
  "copies": 3
}
```

`BookRead` ergänzt `id`. `BookUpdate` erlaubt jedes Feld optional (PATCH).

**`MemberCreate` / `MemberUpdate`**

```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.org",
  "member_since": "2026-01-15"
}
```

`MemberRead` ergänzt `id`.

**`LoanCreate`**

```json
{"book_id": 1, "member_id": 1}
```

**`LoanRead`** – `id`, `book_id`, `member_id`, `lent_at`, `due_at`, `returned_at`
(`null`, solange offen).

**Listen-Envelope** (`BookPage`, `MemberPage`, `LoanPage`):

```json
{"items": [], "total": 0, "limit": 20, "offset": 0}
```

`limit` ist standardmäßig 20 und auf 100 begrenzt, `offset` ist standardmäßig 0.

### Ausleihregeln

- `due_at` = `lent_at` + 14 Tage.
- Höchstens 3 offene Ausleihen je Mitglied.
- Ausleihe nur, solange offene Ausleihen < vorhandene Exemplare.

## Tests

```bash
PYTHONPATH=. py -m pytest
```

Die Suite nutzt den FastAPI-`TestClient` gegen eine eigene, isolierte
SQLite-Testdatenbank.

## Projektstruktur

```
app/
  config.py      # Settings und get_settings()
  database.py    # Engine, Session-Factory, DeclarativeBase, get_session
  models.py      # Book, Member, Loan
  schemas.py     # Pydantic-Schemas und Listen-Envelope
  errors.py      # Einheitlicher Fehlerkörper und Exception-Handler
  security.py    # require_api_key-Dependency
  main.py        # FastAPI-App, Router-Einbindung, /health
  routers/       # books.py, members.py, loans.py
tests/
  conftest.py    # Fixtures: client, api_key, engine
  test_skeleton.py
```
