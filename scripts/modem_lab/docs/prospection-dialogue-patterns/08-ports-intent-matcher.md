# Ports — `IntentMatcherProtocol` (architecture hexagonale)

## Intention du patron

**Ports & adaptateurs** (hexagonal) : le **cœur applicatif** (boucle dialogue) dépend d’**abstractions** (ports), pas d’implémentations concrètes (adaptateurs).

Avantages :

- **tests** : matcher en mémoire qui renvoie toujours un intent fixe ;
- **évolution** : fuzzy match, score de confiance, appel LLM, sans réécrire la boucle modem ;
- **clarité** : le contrat est explicite (`Protocol`).

## Implémentation : `ports.py`

### `IntentMatcherProtocol` (`@runtime_checkable`)

Méthode attendue :

```text
match(transcript: str, pack_dir: Path, rng: random.Random) -> IntentMatchResult | None
```

### Adaptateur concret

`IntentChain` dans `chain.py` implémente cette signature ; `isinstance(chain, IntentMatcherProtocol)` est vrai en Python 3 (sous-typage structurel).

### Côté scénario

`prospection_outbound` déclare `matcher: IntentMatcherProtocol | None` pour documenter l’intention ; l’objet réel reste `IntentChain`.

## Limites actuelles

Les **ports** pour modem pur ou pour Vosk ne sont pas encore formalisés en `Protocol` : seul le matcher d’intentions l’est, car c’est le point le plus probable à **substituer** en test ou en R&D.
