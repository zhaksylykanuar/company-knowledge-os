# FounderOS — PROGRESS

> Живое состояние реализации. Продуктовый источник истины:
> `founderOS_MASTER_PLAYBOOK.md`. Проверяемый ledger:
> `docs/AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас

**FounderOS 2.0 product reset и Temporal Memory v1 реализованы локально в
ветке `codex/living-hq-ux-reset`. Изменения не опубликованы.**

FounderOS теперь определяется как AI-партнёр и второе мнение с доказуемой
памятью компании. Основной интерфейс сокращён до четырёх зон:

- `Сейчас` — один главный вывод, не более двух следующих ситуаций и вход в
  вопрос;
- `Компания` — люди, организации, работа и подтверждающие материалы;
- `Спросить` — отдельная evidence-backed рабочая зона без сохраняемой истории;
- `Настройки` — команда, подключения, API и технические проверки.

Домашний экран теперь различает текущие подтверждённые факты и изменения после
явного персонального checkpoint. Checkpoint хранит только точный snapshot,
время и opaque fingerprints; тексты источников и evidence не копируются.

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
- Добавлен `headquarters.v3` с Temporal Memory v1: `event_time`,
  `observed_at`, evidence, confidence, workspace access и source-bound
  retention.
- Добавлен snapshot-bound checkpoint endpoint и минимальная таблица
  `company_memory_checkpoints`; checkpoint персонален для membership и
  каскадно удаляется при отзыве membership.
- «Подтверждённые факты» после явного checkpoint превращаются в доказуемый
  список новых или изменённых сигналов. Полный lifecycle исчезнувших/закрытых
  событий пока не заявляется.

## Проверено 2026-07-27

- Frontend: `npm test` — **314 passed**.
- Frontend: `npm run typecheck` — успешно.
- Frontend: `npm run build` — успешно, **16 routes**.
- Frontend dependencies: production audit — **0 vulnerabilities**.
- Backend: `uv run ruff check .` — успешно.
- Backend: `uv run pytest -q` — **746 passed**, одно внешнее
  deprecation-предупреждение Starlette/httpx.
- Alembic: единственная head `d6e7f8a9b0c1`, применена к локальной БД.
- Local runtime: `make local-doctor` — все проверки зелёные; backend `8765` и
  web `3000` принадлежат текущему FounderOS.

Authenticated browser QA не засчитан: локальный URL теперь открывается во
встроенном браузере и Chrome, но обе доступные сессии корректно перенаправлены
на `/login` и не содержат авторизации. Пароли/cookies не читались. Доступный
login-screen проверен при ширине `1201` и `390`: horizontal overflow и
console warnings/errors не обнаружены. Это не заменяет QA экранов после входа.

## Следующий рекомендуемый шаг

1. Провести разрешённый authenticated desktop/mobile browser QA.
2. Подтвердить один read-only GitHub App read из рабочей организации и увидеть
   canonical результат внутри `Компания`.
3. Добавить canonical lifecycle event ledger, затем commitments,
   decisions/risks, contradictions и управляемое забывание.

## Неподвижные границы

- Секреты и `.env` значения не попадают в git, UI, логи или документацию.
- Raw storage и Postgres остаются источником истины; Obsidian — только export.
- Значимые утверждения и ActionProposal требуют `evidence_refs`.
- LLM не изменяет production data и не выполняет внешние действия напрямую.
