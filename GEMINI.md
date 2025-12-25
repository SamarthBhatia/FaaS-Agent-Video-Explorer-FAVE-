# AGENTS

## Purpose
This document defines how the FAVE (FaaS-Agent Video Explorer) project is managed when working in this repository. It clarifies files of record, operating rules, and expectations for each session.

## Roles
- **Lead Agent (GEMINI)**: Implements code/data changes, maintains documentation, and keeps status tracking current.
- **Reviewer (User)**: Provides requirements, validates progress, and supplies additional assets (e.g., VideoSearcher sources or datasets).

## Operating Procedure
1. **Plan-first workflow**
   - The canonical plan lives in `PLAN.md`. It describes objectives, milestones, architecture, and detailed tasks.
   - Any change to scope or milestones is reflected in `PLAN.md` before implementation work proceeds.
2. **Status tracking**
   - `status.md` captures task lists with statuses (`done`, `next`, `remaining`) plus session logs.
   - After every material action (code change, documentation update, experiment run), update `status.md` accordingly.
3. **Session routine**
   1. Review `status.md` to pick up previous context.
   2. Execute the planned tasks for the current session.
   3. Update `status.md` (task statuses, session log entry).
   4. Stage, commit, and push changes (one-line commit message, no co-authors).
4. **Artifacts of record**
   - `PLAN.md`: High-level plan and detailed breakdown.  
   - `status.md`: Progress tracker and session history.  
   - Additional docs/code as required by the plan (to be created in future steps).
5. **Version control rules**
   - Every addition/modification/removal triggers `git add`, `git commit` (single-line message), and `git push`.  
   - Only include relevant files in each commit to avoid unrelated noise.  
   - At the end of each working session, the assistant must supply a suggested commit message prefixed with a conventional tag (`feat:`, `docs:`, `fix:`, `test:`, etc.) so the user can manually commit/push when ready.
6. **Communication**
   - If blockers arise (missing assets, tooling limitations, or policy constraints like “no PDF generation”), document them in `status.md` and mention them in the session log for quick resumption.

## Current Focus
Follow the steps enumerated in `PLAN.md` and keep `status.md` synchronized with reality so anyone can resume the project seamlessly.

