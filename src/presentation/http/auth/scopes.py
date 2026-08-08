"""Authorization scopes for the HTTP API (AIA-481, corrected in AIA-675).

Resource-oriented scope model. Four permissions govern the whole surface:

| Permission          | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| ``Search``          | Execute searches (the read-side RAG consumption surface)    |
| ``documents.read``  | Read document/content/chunk/vector data; discovery          |
| ``documents.write`` | Ingest/upload, update metadata, trigger pipeline processing |
| ``admin``           | Destructive deletes, collection/index admin, analytics      |

Two callers, two Entra permission models
----------------------------------------

Entra carries authorization in a different claim depending on how the token was
obtained, and this API has live consumers of both:

- **Delegated scopes** land in the ``scp`` claim (a space-delimited string).
  Issued whenever a user is in the flow — including the on-behalf-of exchange
  the MCP server performs. This is the *only* model available to OBO.
- **App Roles** land in the ``roles`` claim (an array). The only model available
  to app-only / client-credentials callers, which never receive ``scp``.

.. important::
   Entra enforces uniqueness of a permission ``value`` **across** ``appRoles``
   and ``oauth2PermissionScopes`` on a single application — creating the same
   literal in both collections fails with ``DuplicateValue``. A permission
   therefore cannot share one spelling between the two models.

   Each permission consequently has two literals, following the Microsoft Graph
   convention in which the application-permission variant carries a ``.All``
   suffix::

       delegated (scp)   Search       documents.read       documents.write       admin
       app role (roles)  Search.All   documents.read.All   documents.write.All   admin.All

   Routes declare the **delegated** spelling; :func:`accepted_literals` expands
   it to include the App Role spelling, so one declaration serves both caller
   types. See ``dependencies.granted_scopes``.

.. note::
   An earlier revision claimed ``Search`` was an existing **App Role**. It was
   not — ``Search`` exists as a *delegated scope* and is the one literal that is
   compatibility-critical: the MCP server holds an admin-consented grant for it,
   so it must never be renamed or removed. The registration's legacy ``Read`` /
   ``Write`` delegated scopes carry no consent grants and are unused here, as is
   the legacy ``Document.Write`` App Role.

Verb rule of thumb: GET → ``documents.read``, POST/PATCH → ``documents.write``,
DELETE → ``admin``; plus ``Search`` for ``/search/*`` and ``admin`` for
the entire ``/collections/*`` and ``/analytics/*`` surfaces.

There is deliberately **no scope implication in code** — the check in
``get_current_user`` is exact membership. Privileged principals are granted
multiple roles/scopes in Entra (e.g. admins get ``admin`` + ``documents.read``);
``admin`` does NOT automatically grant the others. Expanding a permission to its
``.All`` twin is not an implication: both spellings denote the *same*
permission, differing only in which Entra model issued it.
"""

from enum import StrEnum

# Suffix distinguishing the App Role spelling of a permission from the
# delegated-scope spelling. Required because Entra forbids one value in both.
APP_ROLE_SUFFIX = ".All"


class Scopes(StrEnum):
    """Scope literals used in route ``Security(..., scopes=[...])`` declarations.

    These are the **delegated** spellings. Authorization also accepts the
    corresponding App Role spelling — see :func:`accepted_literals`.
    """

    SEARCH = "Search"
    DOCUMENTS_READ = "documents.read"
    DOCUMENTS_WRITE = "documents.write"
    ADMIN = "admin"


def app_role_for(scope: str) -> str:
    """Return the App Role spelling of a delegated scope literal."""
    return f"{scope}{APP_ROLE_SUFFIX}"


_ACCEPTED_LITERALS: dict[str, frozenset[str]] = {
    scope.value: frozenset({scope.value, app_role_for(scope.value)}) for scope in Scopes
}


def accepted_literals(required: str) -> frozenset[str]:
    """Return every token literal that satisfies ``required``.

    A route requiring ``documents.read`` is satisfied by a delegated token
    carrying ``documents.read`` **or** an app-only token carrying
    ``documents.read.All``. Anything not in the model maps to itself, so an
    unrecognised requirement can only ever be satisfied by an exact match.
    """
    return _ACCEPTED_LITERALS.get(required, frozenset({required}))
