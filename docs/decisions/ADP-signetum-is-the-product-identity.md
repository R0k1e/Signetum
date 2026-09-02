# Signetum is the public product identity

Status: Proposed
Review date: 2026-09-02
Supersedes: ADP-0004-engine-owned-product-site.md
Superseded by: None

## Context

RepoSeal collides with an existing project of the same name. This is the second
time the identity has moved for this reason: DevLoom was dropped because it
"conflicts with established developer products and domains", and the same
sentence applies again. Nothing has been published to the package index, no
repository has been created from the Template, and the tags carry no released
artefact, so the identity can still move at no cost to anyone outside this
repository.

Availability was verified before the name was chosen rather than after. A
*signetum* is a signet: the small seal used to stamp and authenticate a
document. It keeps the accepted meaning — the artefact carries its own proof of
where it came from — and it contains the English word "signet", so a reader
meeting `Signetum-Base:` for the first time can read it without being taught.
Its stress is predictable from the regular English `-etum` family. It sits in
the same Latin register as the sibling runtime Perdura without sharing a brand:
one names endurance, the other names attestation, and neither depends on the
other.

## Decision

The public product identity is **Signetum**, keeping the tagline "Seal every
change with evidence". Everything ADP-0004 decided about the engine owning a
separately deployed product site stands unchanged; only the name it deploys
under moves.

The rename covers the brand: the distribution and import package, the command,
the repository manifest file name, the machine-local state directory, the commit
trailer prefix, and every document and asset which presents the product.

It does not cover the wire contract. The evidence protocol identifier and the
evidence schema, together with its canonical digest, are stable identifiers
which do not follow the product name. A consumer pins them; renaming a brand is
not a reason to break a consumer. They keep their current values, and a decision
to move them is a separate decision with its own consumers to consider.

It does not cover the historical record. Decision files, change package
identities, and changelog entries which name DevLoom or RepoSeal state what was
true when they were written. `ADP-devloom-is-the-public-product-identity.md`
survived the previous rename unaltered and is the precedent: a superseded
decision keeps its name and its content, and a new decision replaces it.
Rewriting them would also break every citation to them, which the traceability
gate now refuses.

## Consequences

- The product has one identity that is free on the package index, on the
  repository host, and on both obvious domains.
- A reader can guess what the name means without knowing Latin.
- Consumers of the evidence protocol are unaffected by the rename.
- The repository keeps a truthful record of having been named twice before.
- A future rename remains possible at the same cost, because the contract layer
  and the brand layer are now separated by decision rather than by memory.
