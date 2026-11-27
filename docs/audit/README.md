# Audits and historical decisions

[Documentation index](../README.md)

This folder is a historical record. Records keep their original language and the measurement context of the branch they describe. They are evidence of a decision, not current documentation of the code: where a record and a guide disagree, the guide describes the present state. A later measurement is appended with its date rather than silently rewriting the earlier one.

| File | Record |
|---|---|
| [0001-migration-parallele.md](0001-migration-parallele.md) | ADR: modular migration by parallel implementation. |
| [0002-cloture.md](0002-cloture.md) | ADR: closure of the modular migration and its debt. |
| [0003-typed-ports.md](0003-typed-ports.md) | ADR: tightening the types of the package ports. |
| [0004-typing-core.md](0004-typing-core.md) | ADR: typing the simulation core and the JSON boundary. |
| [0005-decasts.md](0005-decasts.md) | ADR: removing redundant casts from the typed seams. |
| [ecs-spike-2026-11.md](ecs-spike-2026-11.md) | ADR: falsification spike for an ECS migration, measured NO-GO. |
| [ecs-migration-decision.md](ecs-migration-decision.md) | ADR: the user overrode that NO-GO and requested the migration anyway. |
| [hitbox-feel-2026-11-18.md](hitbox-feel-2026-11-18.md) | Full hitbox and combo-feel audit, with the baseline defects and fixes. |
| [performance-2026-11.md](performance-2026-11.md) | Performance measurements and the phases that followed. |
| [phase-e-plan.md](phase-e-plan.md) | Optional structural optimizations and the gates they require. |

## Related historical notes

These records live outside this folder but are part of the same history.

| File | Record |
|---|---|
| [Level matrix design](../design/matrice-niveaux.md) | Unimplemented design proposal for rooms laid out as a matrix. |

> **Note** - Current performance tooling is documented in [Benchmarks](../guides/benchmarks.md), the present rendering pipeline in [Rendering pipeline](../architecture/rendering.md), and the shipped frame-data timing policy in [Combat and physics](../architecture/combat-and-physics.md).
