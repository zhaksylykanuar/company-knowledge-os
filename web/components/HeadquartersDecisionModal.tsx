"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type RefObject
} from "react";

import {
  createLocalActionDecisionIdempotencyKey,
  isAmbiguousLocalActionDecisionFailure,
  LocalActionDecisionContractError,
  localDecisionLabel,
  submitLocalActionDecisionWithOneRetry,
  type LocalActionDecision
} from "../lib/action-proposal-decision";
import { ApiRequestError, fetchActionProposal } from "../lib/api";
import type {
  HeadquartersMission,
  HeadquartersSnapshotResponse
} from "../lib/headquarters";
import type {
  ActionProposal,
  LocalActionDecisionReceipt
} from "../lib/types";
import { useSession } from "../lib/session";
import { EvidenceList } from "./HeadquartersMissionDetail";
import { OverlayShell } from "./OverlayShell";

export type DecisionStatus = "error" | "loading" | "ready" | "receipt" | "stale";
type RefetchStatus = "idle" | "pending" | "failed" | "succeeded";

export type LocalDecisionAttempt = {
  decision: LocalActionDecision;
  idempotencyKey: string;
};

export function HeadquartersDecisionModal({
  backgroundRef,
  mission,
  onClose,
  onRefetch,
  snapshot
}: {
  backgroundRef: RefObject<HTMLElement | null>;
  mission: HeadquartersMission;
  onClose: () => void;
  onRefetch: () => Promise<HeadquartersSnapshotResponse>;
  snapshot: HeadquartersSnapshotResponse;
}) {
  const session = useSession();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [proposal, setProposal] = useState<ActionProposal | null>(null);
  const [receipt, setReceipt] = useState<LocalActionDecisionReceipt | null>(null);
  const [refetchStatus, setRefetchStatus] = useState<RefetchStatus>("idle");
  const [status, setStatus] = useState<DecisionStatus>("loading");
  const attemptRef = useRef<LocalDecisionAttempt | null>(null);
  const receiptHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const proposalId = mission.proposal_id;

  useEffect(() => {
    session?.setExternalOperationPending(pending);
    return () => {
      if (pending) session?.setExternalOperationPending(false);
    };
  }, [pending, session]);

  useEffect(() => {
    if (!proposalId || !mission.proposal_version) {
      setError("У этой ситуации нет точной версии решения.");
      setStatus("stale");
      return;
    }
    const controller = new AbortController();
    setError(null);
    setStatus("loading");
    fetchActionProposal(snapshot.workspace.id, proposalId, {
      signal: controller.signal
    })
      .then((loaded) => {
        if (
          loaded.id !== proposalId ||
          loaded.workspace_id !== snapshot.workspace.id ||
          loaded.proposal_version !== mission.proposal_version
        ) {
          setError("Решение изменилось после формирования этого снимка.");
          setStatus("stale");
          return;
        }
        setProposal(loaded);
        setStatus("ready");
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setError(decisionLoadError(caught));
        setStatus(caught instanceof ApiRequestError && caught.status === 409 ? "stale" : "error");
      });
    return () => controller.abort();
  }, [mission.proposal_version, proposalId, snapshot.workspace.id]);

  useEffect(() => {
    if (status === "receipt") {
      receiptHeadingRef.current?.focus({ preventScroll: true });
    }
  }, [status]);

  async function decide(decision: LocalActionDecision) {
    if (!proposal || pending || status !== "ready") return;
    const attempt = resolveLocalDecisionAttempt(
      attemptRef.current,
      decision,
      proposal.id
    );
    attemptRef.current = attempt;
    setError(null);
    setPending(true);
    try {
      const response = await submitLocalActionDecisionWithOneRetry({
        decision,
        expectedSnapshotId: snapshot.snapshot.id,
        idempotencyKey: attempt.idempotencyKey,
        proposal,
        reason:
          decision === "rejected"
            ? "Отклонено в FounderOS после проверки подтверждённых оснований."
            : null,
        workspaceId: snapshot.workspace.id
      });
      setProposal(response.proposal);
      setReceipt(response.decision_receipt);
      setStatus("receipt");
      attemptRef.current = null;
      await refreshAfterReceipt();
    } catch (caught: unknown) {
      setError(decisionSubmitError(caught));
      setStatus(decisionStatusAfterSubmitFailure(caught));
    } finally {
      setPending(false);
    }
  }

  async function refreshAfterReceipt() {
    setRefetchStatus("pending");
    try {
      await onRefetch();
      setRefetchStatus("succeeded");
    } catch {
      setRefetchStatus("failed");
    }
  }

  const canReview = snapshot.capabilities.can_review_proposal;
  return (
    <OverlayShell
      backgroundRef={backgroundRef}
      closeDisabled={pending}
      closeLabel="Закрыть решение"
      label="Решение по ситуации"
      mode="modal"
      onClose={onClose}
    >
      <HeadquartersDecisionContent
        canReview={canReview}
        error={error}
        mission={mission}
        onApprove={() => void decide("approved")}
        onClose={onClose}
        onRefetch={() => void refreshAfterReceipt()}
        onReject={() => void decide("rejected")}
        pending={pending}
        proposal={proposal}
        receipt={receipt}
        receiptHeadingRef={receiptHeadingRef}
        refetchStatus={refetchStatus}
        status={status}
      />
    </OverlayShell>
  );
}

export function HeadquartersDecisionContent({
  canReview,
  error,
  mission,
  onApprove,
  onClose,
  onRefetch,
  onReject,
  pending,
  proposal,
  receipt,
  receiptHeadingRef,
  refetchStatus,
  status
}: {
  canReview: boolean;
  error: string | null;
  mission: HeadquartersMission;
  onApprove?: () => void;
  onClose?: () => void;
  onRefetch?: () => void;
  onReject?: () => void;
  pending: boolean;
  proposal: ActionProposal | null;
  receipt: LocalActionDecisionReceipt | null;
  receiptHeadingRef?: RefObject<HTMLHeadingElement | null>;
  refetchStatus: RefetchStatus;
  status: DecisionStatus;
}) {
  if (status === "loading") {
    return <p className="headquarters-decision-state" aria-busy="true">Проверяем точное решение…</p>;
  }
  if (status === "receipt" && receipt) {
    return (
      <section className="headquarters-decision-receipt" role="status">
        <span className="headquarters-decision-mark" aria-hidden="true">✓</span>
        <span className="eyebrow">Локальная квитанция сохранена</span>
        <h3 ref={receiptHeadingRef} tabIndex={-1}>
          Решение: {localDecisionLabel(receipt.decision)}
        </h3>
        <p>
          FounderOS сохранил решение человека. Во внешние сервисы ничего не
          отправлялось.
        </p>
        <dl className="headquarters-decision-receipt-facts">
          <div><dt>Квитанция</dt><dd>{shortReceiptId(receipt.receipt_id)}</dd></div>
          <div><dt>Записано</dt><dd>{formatDecisionDate(receipt.recorded_at)}</dd></div>
          <div><dt>Внешняя запись</dt><dd>Нет</dd></div>
        </dl>
        {refetchStatus === "pending" ? (
          <p aria-live="polite">Обновляем приоритет FounderOS…</p>
        ) : refetchStatus === "failed" ? (
          <p className="headquarters-decision-warning" role="status">
            Квитанция сохранена, но новый снимок пока не загрузился.
          </p>
        ) : refetchStatus === "succeeded" ? (
          <p className="headquarters-decision-success" role="status">
            FounderOS обновлён и пересчитал следующий ход.
          </p>
        ) : null}
        <div className="headquarters-decision-actions">
          {refetchStatus === "failed" ? (
            <button onClick={onRefetch} type="button">Повторить обновление</button>
          ) : null}
          <button disabled={refetchStatus === "pending"} onClick={onClose} type="button">
            Вернуться в FounderOS
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className="headquarters-decision">
      <span className="eyebrow">Точный ход · {mission.id}</span>
      <h3>{mission.title}</h3>
      <section>
        <strong>Почему сейчас</strong>
        <p>{mission.why_now}</p>
      </section>
      <section>
        <strong>Что произойдёт</strong>
        <p>
          {proposal?.target_provider === "internal"
            ? "Решение останется внутри FounderOS."
            : "Сейчас сохранится только решение. Любое внешнее действие остаётся отдельным шагом вне этого окна."}
        </p>
      </section>
      <EvidenceList evidence={mission.evidence_refs} heading="Подтверждённые основания" />
      {error ? <p className="headquarters-decision-warning" role="alert">{error}</p> : null}
      {status === "stale" || status === "error" ? (
        <div className="headquarters-decision-actions">
          {mission.proposal_id ? (
            <Link href={`/actions?proposal=${encodeURIComponent(mission.proposal_id)}`}>
              Открыть точную историю
            </Link>
          ) : null}
          <button onClick={onClose} type="button">Вернуться в FounderOS</button>
        </div>
      ) : proposal?.status !== "proposed" ? (
        <p>Текущее состояние решения: {proposal?.status ?? "неизвестно"}.</p>
      ) : canReview ? (
        <div className="headquarters-decision-actions">
          <button disabled={pending} onClick={onApprove} type="button">
            {pending ? "Сохраняем…" : "Принять локально"}
          </button>
          <button disabled={pending} onClick={onReject} type="button">
            Отклонить
          </button>
        </div>
      ) : (
        <div className="headquarters-decision-readonly">
          <strong>Только просмотр</strong>
          <p>Решение может принять администратор или владелец компании.</p>
        </div>
      )}
    </div>
  );
}

function decisionLoadError(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 404) {
    return "Решение больше не существует в этой компании.";
  }
  if (error instanceof ApiRequestError && error.status === 403) {
    return "Нет доступа к этому решению.";
  }
  return error instanceof Error ? error.message : "Не удалось загрузить решение.";
}

function decisionSubmitError(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 409) {
    return "Снимок или решение изменились. Обновите FounderOS и проверьте новый контекст.";
  }
  if (error instanceof ApiRequestError && error.status === 403) {
    return "Нет доступа к сохранению этого решения.";
  }
  if (error instanceof ApiRequestError && error.status === 404) {
    return "Решение больше не существует в этой компании.";
  }
  if (error instanceof LocalActionDecisionContractError) {
    return "Сервер не подтвердил точную локальную квитанцию после автоматического повтора. Повтор из этого окна заблокирован.";
  }
  if (isAmbiguousLocalActionDecisionFailure(error)) {
    return "Результат не подтверждён после автоматического повтора. Можно повторить вручную — FounderOS использует тот же ключ операции.";
  }
  return error instanceof Error
    ? error.message
    : "Не удалось подтвердить результат. Повтор без проверки заблокирован.";
}

export function resolveLocalDecisionAttempt(
  current: LocalDecisionAttempt | null,
  decision: LocalActionDecision,
  proposalId: string
): LocalDecisionAttempt {
  if (current?.decision === decision) return current;
  return {
    decision,
    idempotencyKey: createLocalActionDecisionIdempotencyKey(proposalId, decision)
  };
}

export function decisionStatusAfterSubmitFailure(
  error: unknown
): "error" | "ready" | "stale" {
  if (error instanceof ApiRequestError && error.status === 409) {
    return "stale";
  }
  if (error instanceof LocalActionDecisionContractError) {
    return "error";
  }
  return isAmbiguousLocalActionDecisionFailure(error) ? "ready" : "error";
}

function shortReceiptId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function formatDecisionDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Время не подтверждено"
    : new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
}
