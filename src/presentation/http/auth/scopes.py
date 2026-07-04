"""Authorization scopes for the HTTP API (AIA-481).

Resource-oriented scope model mapped to Microsoft Entra **App Roles** (the
``roles`` claim read by ``TokenValidator`` / ``get_current_user``), not
delegated ``scp`` scopes — so the same model works for both user and
app-only (M2M) tokens.

| Scope               | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| ``Search``          | Execute searches (the read-side RAG consumption surface)    |
| ``documents.read``  | Read document/content/chunk/vector data; discovery          |
| ``documents.write`` | Ingest/upload, update metadata, trigger pipeline processing |
| ``admin``           | Destructive deletes, collection/index admin, analytics      |

``Search`` matches the App Role value that already exists in the Entra app
registration — scope literals here must mirror the registration exactly.

Verb rule of thumb: GET → ``documents.read``, POST/PATCH → ``documents.write``,
DELETE → ``admin``; plus ``Search`` for ``/search/*`` and ``admin`` for
the entire ``/collections/*`` and ``/analytics/*`` surfaces.

There is deliberately **no scope implication in code** — the check in
``get_current_user`` is exact membership. Privileged principals are granted
multiple App Roles in Entra (e.g. admins get ``admin`` + ``documents.read``);
``admin`` does NOT automatically grant the others.
"""

from enum import StrEnum


class Scopes(StrEnum):
    """Scope literals used in route ``Security(..., scopes=[...])`` declarations."""

    SEARCH = "Search"
    DOCUMENTS_READ = "documents.read"
    DOCUMENTS_WRITE = "documents.write"
    ADMIN = "admin"
