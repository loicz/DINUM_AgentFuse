"""Transport JSON borné et liaison v0, identiques pour exemples et intégrations."""

import hashlib
import json
from typing import TypeVar

from .contracts import Contract, EvaluationRequest

MAX_JSON_BYTES = 262144
MAX_JSON_DEPTH = 24
T = TypeVar("T", bound=Contract)


class ContractError(ValueError):
    """Entrée invalide ; ne jamais exécuter ni journaliser le contenu rejeté."""


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("Clé JSON dupliquée.")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ContractError("Nombre JSON non fini.")


def parse_json(model: type[T], raw: str) -> T:
    """Point d'entrée des octets non fiables, avant toute utilisation d'un DTO."""
    try:
        if len(raw) > MAX_JSON_BYTES or len(raw.encode("utf-8")) > MAX_JSON_BYTES:
            raise ContractError("JSON trop volumineux.")
        decoded = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        stack = [(decoded, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ContractError("JSON trop profond.")
            if isinstance(value, (dict, list)):
                children = value.values() if isinstance(value, dict) else value
                stack.extend((child, depth + 1) for child in children)
        # Le mode JSON strict accepte les tableaux JSON comme tuples Python.
        return model.model_validate_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("Contrat JSON invalide ; aucune action autorisée.") from None


def canonical_json(value: Contract) -> str:
    """UTF-8, clés triées, sans espaces, valeurs exactes ; aucun flottant dans v0."""
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def action_binding(request: EvaluationRequest) -> str:
    """Empreinte, pas signature : l'approbation reste vérifiée en stockage serveur.

    L'heure de vérification et le grant sont exclus pour permettre une nouvelle
    évaluation de la même action ; les versions de droits/exposition sont incluses.
    """
    data = {
        "binding_version": "pilot-v1",
        "resource_source": request.resource_source.model_dump(mode="json") if request.resource_source else None,
        "action": request.action.model_dump(mode="json"),
        "scope": request.snapshot.scope.model_dump(mode="json"),
        "policy": request.policy.model_dump(mode="json"),
        "exposure": request.snapshot.exposure.model_dump(mode="json"),
        "evidence": [e.model_dump(mode="json") for e in request.snapshot.evidence],
        "permissions_version": request.snapshot.authorization.permissions_version,
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
