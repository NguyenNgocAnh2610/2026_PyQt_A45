# Mẫu file task: .agent-orchestrator/tasks/T-XXX.md

```markdown
# T-XXX — Tên tác vụ

## Objective
Một kết quả đầu ra, mô tả đo/kiểm thử được.

## Scope
- Allowed files: ...
- Do not touch: AGENTS.md, CLAUDE.md, PROGRESS.md, .env, credentials

## Context
- Read AGENTS.md and relevant docs, code, tests.
- Relevant decisions/dependencies: ...
- Do not assume the source state matches PROGRESS.md without checking.

## Acceptance criteria
- [ ] ...
- [ ] Tests ...

## Verification
- Exact test commands: ...
- Expected behavior: ...

## Safety
- No production access/hardware operation/secret exposure.
- No git commit/push/merge.

## Output format
Return: status; files changed; summary; commands/tests with observed results; risks; limitations; suggested follow-ups.
```

Claude phải thêm điều kiện chặn tác vụ thiếu thông tin quan trọng. Worker chỉ báo kết quả; Claude giữ quyền chỉnh `PROGRESS.md`.
