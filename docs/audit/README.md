# Audits and historical decisions

[Documentation index](../README.md)

This folder is a historical record. Its files are kept exactly as they were written, including their original language and the measurement context of the branch they describe. They are evidence of a decision, not current documentation of the code: where a record and a guide disagree, the guide describes the present state.

| File | Record |
|---|---|
| [ecs-spike-2026-11.md](ecs-spike-2026-11.md) | ADR: falsification spike for an ECS migration, measured NO-GO. |
| [ecs-migration-decision.md](ecs-migration-decision.md) | ADR: the user overrode that NO-GO and requested the migration anyway. |
| [final-cleanup-2026-11.md](final-cleanup-2026-11.md) | Final verification of the restructuring branch. |
| [hitbox-feel-2026-11-18.md](hitbox-feel-2026-11-18.md) | Full hitbox and combo-feel audit, with the baseline defects and fixes. |
| [performance-2026-11.md](performance-2026-11.md) | Performance measurements and the phases that followed. |
| [phase-e-plan.md](phase-e-plan.md) | Optional structural optimizations and the gates they require. |

## Related historical notes

These records live outside this folder but are part of the same history.

| File | Record |
|---|---|
| [Playtest notes](../playtest-2026-11-18.md) | Manual checklist of combat feel from November 2026. |
| [Hitbox fluidity PR notes](../pr-fix-hitbox-fluidity.md) | Reasoning and measurements behind the hitbox feel fix. |
| [Level matrix design](../design/matrice-niveaux.md) | Unimplemented design proposal for rooms laid out as a matrix. |

> **Note** - Current performance tooling is documented in [Benchmarks](../guides/benchmarks.md), and the present rendering pipeline in [Rendering pipeline](../architecture/rendering.md).
