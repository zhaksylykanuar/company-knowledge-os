# FounderOS — PROGRESS

> Живое состояние реализации. Продуктовый источник истины:
> `founderOS_MASTER_PLAYBOOK.md`. Проверяемый ledger:
> `docs/AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас

**FounderOS 2.0 product reset реализован локально в ветке
`codex/living-hq-ux-reset`. Изменения не опубликованы.**

FounderOS теперь определяется как AI-партнёр и второе мнение с доказуемой
памятью компании. Основной интерфейс сокращён до четырёх зон:

- `Сейчас` — один главный вывод, не более двух следующих ситуаций и вход в
  вопрос;
- `Компания` — люди, организации, работа и подтверждающие материалы;
- `Спросить` — отдельная evidence-backed рабочая зона без сохраняемой истории;
- `Настройки` — команда, подключения, API и технические проверки.

## Что изменено

- Заменён legacy playbook и удалён старый Living Command Center ledger.
- Удалены runtime `/demo`, synthetic demo code, старые Today/Living HQ модели,
  мини-карта и их тесты.
- Удалены product routes `/connectors`, `/github`, `/jira`, `/gmail`, `/drive`.
  GitHub setup перенесён в `/settings/integrations/github`; все остальные
  подключения находятся в `/settings/integrations`.
- Удалены provider-first и старые primary labels из пользовательского shell.
- Домашняя страница перестроена вокруг текущей картины и прямого вопроса к
  FounderOS; техническое состояние источников убрано из основного экрана.
- `Спросить` сделан самостоятельным экраном поверх exact workspace snapshot.
  История диалога не сохраняется, provider calls и внешние записи не
  выполняются.
- Сохранены raw storage/Postgres truth, evidence, tenancy, RBAC, human approval,
  idempotency и receipts.
- Исправлен GitHub App fallback redirect на новый settings route.
- Удалены неиспользуемые старые тексты и CSS-блоки Command Center, Today,
  provider pulse и source-health drawer.

## Проверено 2026-07-25

- Frontend: `npm test` — **312 passed**. Superseded component-only suites were
  deleted together with their unreachable UI.
- Frontend: `npm run typecheck` — успешно.
- Frontend: `npm run build` — успешно, **16 routes**.
- Frontend dependencies: production audit — **0 vulnerabilities**.
- Backend: `uv run ruff check .` — успешно.
- Backend: `uv run pytest -q` — **745 passed**, одно внешнее
  deprecation-предупреждение Starlette/httpx.
- Local runtime: `make local-doctor` — все проверки зелёные; backend `8765` и
  web `3000` принадлежат текущему FounderOS.

Browser QA не засчитан: локальный runtime запущен, но встроенный browser
отклонил переход к local URL политикой безопасности. Это не заменяется
Playwright/CDP обходом.

## Следующий рекомендуемый шаг

1. Провести разрешённый authenticated desktop/mobile browser QA.
2. Подтвердить один read-only GitHub App read из рабочей организации и увидеть
   canonical результат внутри `Компания`.
3. Затем переходить к temporal memory: event/observed time, commitments,
   contradictions, checkpoints и управляемое забывание.

## Неподвижные границы

- Секреты и `.env` значения не попадают в git, UI, логи или документацию.
- Raw storage и Postgres остаются источником истины; Obsidian — только export.
- Значимые утверждения и ActionProposal требуют `evidence_refs`.
- LLM не изменяет production data и не выполняет внешние действия напрямую.
