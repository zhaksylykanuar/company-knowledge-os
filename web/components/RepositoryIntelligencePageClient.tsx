"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchRepositoryIntelligenceDetail,
  fetchRepositoryIntelligenceGraph,
  fetchRepositoryIntelligenceHistory,
  fetchRepositoryIntelligencePortfolio,
  type RepositoryDetailResponse,
  type RepositoryEvidence,
  type RepositoryFact,
  type RepositoryGraphEdge,
  type RepositoryGraphResponse,
  type RepositoryHistoryResponse,
  type RepositoryPortfolioItem,
  type RepositoryPortfolioResponse
} from "../lib/repository-intelligence";
import { useWorkspaceId } from "../lib/session";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { LoadingState } from "./LoadingState";
import { PageHeader } from "./PageHeader";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";
import styles from "./repository-intelligence.module.css";

type PageStatus = "loading" | "ready" | "empty" | "error" | "missing";
type DetailStatus = "idle" | "loading" | "ready" | "error";
type ViewMode = "portfolio" | "graph";

type PortfolioFilters = {
  query: string;
  repositoryType: string;
  product: string;
  owner: "all" | "confirmed" | "unresolved";
  lifecycle: "all" | "active" | "archived";
  severity: "all" | "critical" | "high" | "medium" | "low" | "info";
  staleness: "all" | "fresh" | "stale";
};

const DEFAULT_FILTERS: PortfolioFilters = {
  query: "",
  repositoryType: "all",
  product: "all",
  owner: "all",
  lifecycle: "all",
  severity: "all",
  staleness: "all"
};

export function RepositoryIntelligencePageClient({
  initialRepositoryId
}: {
  initialRepositoryId: string | null;
}) {
  const workspaceId = useWorkspaceId();
  const [portfolio, setPortfolio] =
    useState<RepositoryPortfolioResponse | null>(null);
  const [graph, setGraph] = useState<RepositoryGraphResponse | null>(null);
  const [detail, setDetail] = useState<RepositoryDetailResponse | null>(null);
  const [history, setHistory] =
    useState<RepositoryHistoryResponse | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string | null>(
    initialRepositoryId
  );
  const [status, setStatus] = useState<PageStatus>("loading");
  const [detailStatus, setDetailStatus] = useState<DetailStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    void reloadKey;
    if (!workspaceId) {
      setPortfolio(null);
      setGraph(null);
      setDetail(null);
      setHistory(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    setPortfolio(null);
    setGraph(null);
    setDetail(null);
    setHistory(null);
    setSelectedRepositoryId(null);
    setDetailStatus("idle");
    Promise.all([
      fetchRepositoryIntelligencePortfolio(workspaceId),
      fetchRepositoryIntelligenceGraph(workspaceId)
    ])
      .then(([portfolioPayload, graphPayload]) => {
        if (cancelled) {
          return;
        }
        setPortfolio(portfolioPayload);
        setGraph(graphPayload);
        setStatus(
          portfolioPayload.repositories.length > 0 ? "ready" : "empty"
        );
        const requested = initialRepositoryId
          ? portfolioPayload.repositories.find(
              (repository) => repository.id === initialRepositoryId
            )?.id ?? null
          : null;
        setSelectedRepositoryId(
          requested ?? portfolioPayload.repositories[0]?.id ?? null
        );
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setPortfolio(null);
        setGraph(null);
        setStatus("error");
        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось загрузить Repository Intelligence."
        );
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, initialRepositoryId, reloadKey]);

  useEffect(() => {
    if (
      !workspaceId ||
      !selectedRepositoryId ||
      portfolio?.workspace_id !== workspaceId ||
      !portfolio.repositories.some(
        (repository) => repository.id === selectedRepositoryId
      )
    ) {
      setDetail(null);
      setHistory(null);
      setDetailStatus("idle");
      return;
    }

    let cancelled = false;
    setDetailStatus("loading");
    setDetailError(null);
    Promise.all([
      fetchRepositoryIntelligenceDetail(workspaceId, selectedRepositoryId),
      fetchRepositoryIntelligenceHistory(workspaceId, selectedRepositoryId)
    ])
      .then(([detailPayload, historyPayload]) => {
        if (cancelled) {
          return;
        }
        setDetail(detailPayload);
        setHistory(historyPayload);
        setDetailStatus("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setDetail(null);
        setHistory(null);
        setDetailStatus("error");
        setDetailError(
          caught instanceof Error
            ? caught.message
            : "Не удалось открыть карточку репозитория."
        );
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, selectedRepositoryId, portfolio]);

  return (
    <RepositoryIntelligenceView
      detail={detail}
      detailError={detailError}
      detailStatus={detailStatus}
      error={error}
      graph={graph}
      history={history}
      onRetry={() => setReloadKey((current) => current + 1)}
      onSelectRepository={setSelectedRepositoryId}
      portfolio={portfolio}
      selectedRepositoryId={selectedRepositoryId}
      status={status}
    />
  );
}

export function RepositoryIntelligenceView({
  detail,
  detailError,
  detailStatus,
  error,
  graph,
  history,
  onRetry,
  onSelectRepository,
  portfolio,
  selectedRepositoryId,
  status
}: {
  detail: RepositoryDetailResponse | null;
  detailError: string | null;
  detailStatus: DetailStatus;
  error: string | null;
  graph: RepositoryGraphResponse | null;
  history: RepositoryHistoryResponse | null;
  onRetry?: () => void;
  onSelectRepository: (repositoryId: string) => void;
  portfolio: RepositoryPortfolioResponse | null;
  selectedRepositoryId: string | null;
  status: PageStatus;
}) {
  const [filters, setFilters] = useState<PortfolioFilters>(DEFAULT_FILTERS);
  const [viewMode, setViewMode] = useState<ViewMode>("portfolio");
  const [selectedEvidence, setSelectedEvidence] = useState<{
    evidence: RepositoryEvidence;
    title: string;
  } | null>(null);

  const filteredRepositories = useMemo(
    () =>
      filterRepositoryPortfolio(
        portfolio?.repositories ?? [],
        filters
      ),
    [portfolio, filters]
  );
  const repositoryTypes = uniqueValues(
    portfolio?.repositories.map((repository) => repository.repository_type) ?? []
  );
  const products = uniqueValues(
    portfolio?.repositories.flatMap(
      (repository) => repository.product_candidates
    ) ?? []
  );

  return (
    <div className={styles.page}>
      <PageHeader
        description="Назначение, связи, риски, неизвестные и история аудита — только из сохранённых RI-006 данных."
        eyebrow="Repository Intelligence"
        title="Карта репозиториев"
      />
      <div className={styles.breadcrumb}>
        <Link href="/company-brain">Компания</Link>
        <span aria-hidden="true">/</span>
        <span>Репозитории</span>
      </div>

      {status === "loading" ? (
        <LoadingState label="Загружаем карту репозиториев…" />
      ) : null}
      {status === "missing" ? (
        <EmptyState
          description="Выберите рабочее пространство, чтобы открыть его Repository Intelligence."
          title="Компания не выбрана"
        />
      ) : null}
      {status === "error" ? (
        <section className={styles.stateStack}>
          <ErrorState
            description={error ?? "Repository Intelligence недоступен."}
            title="Не удалось загрузить карту репозиториев"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Повторить
          </button>
        </section>
      ) : null}
      {status === "empty" ? (
        <EmptyState
          description="В этом рабочем пространстве пока нет канонических репозиториев. RI-007 не запускает синхронизацию или анализ."
          title="Репозитории пока не подготовлены"
        />
      ) : null}

      {portfolio && status === "ready" ? (
        <>
          <Summary portfolio={portfolio} />
          <div className={styles.modeTabs} role="tablist" aria-label="Вид карты">
            <button
              aria-selected={viewMode === "portfolio"}
              className={viewMode === "portfolio" ? styles.activeTab : ""}
              onClick={() => setViewMode("portfolio")}
              role="tab"
              type="button"
            >
              Портфель
            </button>
            <button
              aria-selected={viewMode === "graph"}
              className={viewMode === "graph" ? styles.activeTab : ""}
              onClick={() => setViewMode("graph")}
              role="tab"
              type="button"
            >
              Направленные связи
            </button>
          </div>

          {viewMode === "portfolio" ? (
            <>
              <PortfolioFilters
                filters={filters}
                onChange={setFilters}
                products={products}
                repositoryTypes={repositoryTypes}
              />
              <div className={styles.workspace}>
                <RepositoryList
                  onSelect={(repositoryId) => {
                    setSelectedEvidence(null);
                    onSelectRepository(repositoryId);
                  }}
                  repositories={filteredRepositories}
                  selectedRepositoryId={selectedRepositoryId}
                />
                <RepositoryDetail
                  detail={detail}
                  error={detailError}
                  history={history}
                  onEvidence={(evidence, title) =>
                    setSelectedEvidence({ evidence, title })
                  }
                  status={detailStatus}
                />
                <RepositoryEvidenceDrawer
                  selected={selectedEvidence}
                  onClose={() => setSelectedEvidence(null)}
                />
              </div>
            </>
          ) : (
            <RelationshipGraph graph={graph} />
          )}

          <p className={styles.boundary}>
            Только чтение PostgreSQL RI-006: без provider calls, checkout,
            выполнения кода, LLM и внешних действий. Raw source bodies,
            evidence quotes и artifact paths не возвращаются.
          </p>
        </>
      ) : null}
    </div>
  );
}

function Summary({ portfolio }: { portfolio: RepositoryPortfolioResponse }) {
  return (
    <section className="grid" aria-label="Сводка Repository Intelligence">
      <StatusCard
        description="Канонические репозитории текущей компании."
        title="Репозитории"
        value={String(portfolio.summary.repositories)}
      />
      <StatusCard
        description="Репозитории с хотя бы одним сохранённым аудитом."
        title="Аудированы"
        value={String(portfolio.summary.analyzed_repositories)}
      />
      <StatusCard
        description="Текущие направленные связи между репозиториями."
        title="Связи"
        value={String(portfolio.summary.current_relationships)}
      />
      <StatusCard
        description="Открытые вопросы без достаточного доказательства."
        title="Неизвестные"
        value={String(portfolio.summary.blocking_unknowns)}
      />
    </section>
  );
}

function PortfolioFilters({
  filters,
  onChange,
  products,
  repositoryTypes
}: {
  filters: PortfolioFilters;
  onChange: (filters: PortfolioFilters) => void;
  products: string[];
  repositoryTypes: string[];
}) {
  return (
    <section className={styles.filters} aria-label="Фильтры портфеля">
      <label className={styles.search}>
        <span>Поиск</span>
        <input
          onChange={(event) =>
            onChange({ ...filters, query: event.target.value })
          }
          placeholder="owner/repo или назначение"
          type="search"
          value={filters.query}
        />
      </label>
      <FilterSelect
        label="Тип"
        onChange={(repositoryType) =>
          onChange({ ...filters, repositoryType })
        }
        options={repositoryTypes}
        value={filters.repositoryType}
      />
      <FilterSelect
        label="Продукт"
        onChange={(product) => onChange({ ...filters, product })}
        options={products}
        value={filters.product}
      />
      <FilterSelect
        label="Владелец"
        onChange={(owner) =>
          onChange({
            ...filters,
            owner: owner as PortfolioFilters["owner"]
          })
        }
        options={["confirmed", "unresolved"]}
        value={filters.owner}
      />
      <FilterSelect
        label="Жизненный цикл"
        onChange={(lifecycle) =>
          onChange({
            ...filters,
            lifecycle: lifecycle as PortfolioFilters["lifecycle"]
          })
        }
        options={["active", "archived"]}
        value={filters.lifecycle}
      />
      <FilterSelect
        label="Severity"
        onChange={(severity) =>
          onChange({
            ...filters,
            severity: severity as PortfolioFilters["severity"]
          })
        }
        options={["critical", "high", "medium", "low", "info"]}
        value={filters.severity}
      />
      <FilterSelect
        label="Свежесть"
        onChange={(staleness) =>
          onChange({
            ...filters,
            staleness: staleness as PortfolioFilters["staleness"]
          })
        }
        options={["fresh", "stale"]}
        value={filters.staleness}
      />
    </section>
  );
}

function FilterSelect({
  label,
  onChange,
  options,
  value
}: {
  label: string;
  onChange: (value: string) => void;
  options: string[];
  value: string;
}) {
  return (
    <label className={styles.filter}>
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="all">Все</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function RepositoryList({
  onSelect,
  repositories,
  selectedRepositoryId
}: {
  onSelect: (repositoryId: string) => void;
  repositories: RepositoryPortfolioItem[];
  selectedRepositoryId: string | null;
}) {
  return (
    <section className={styles.repositoryList} aria-label="Портфель репозиториев">
      <div className={styles.sectionTitle}>
        <h2>Репозитории</h2>
        <span>{repositories.length}</span>
      </div>
      {repositories.length === 0 ? (
        <p className="muted">Для выбранных фильтров репозиториев нет.</p>
      ) : null}
      {repositories.map((repository) => (
        <button
          aria-pressed={selectedRepositoryId === repository.id}
          className={`${styles.repositoryCard} ${
            selectedRepositoryId === repository.id ? styles.selectedCard : ""
          }`}
          key={repository.id}
          onClick={() => onSelect(repository.id)}
          type="button"
        >
          <span className={styles.cardTopline}>
            <strong>{repository.full_name}</strong>
            <ClaimBadge
              humanResolution="pending"
              status={repository.purpose_status}
            />
          </span>
          <span className={styles.repositoryType}>
            {repository.repository_type}
          </span>
          <span className={styles.cardPurpose}>
            {repository.purpose_summary ?? "Назначение пока не доказано."}
          </span>
          <span className={styles.cardMetrics}>
            <span>Связи: {repository.outbound_relationship_count + repository.inbound_relationship_count}</span>
            <span>Риски: {repository.open_findings_total}</span>
            <span>Неизвестные: {repository.unknown_count}</span>
          </span>
          {repository.has_stale_intelligence ? (
            <span className={styles.stale}>Есть устаревшие факты</span>
          ) : null}
        </button>
      ))}
    </section>
  );
}

function RepositoryDetail({
  detail,
  error,
  history,
  onEvidence,
  status
}: {
  detail: RepositoryDetailResponse | null;
  error: string | null;
  history: RepositoryHistoryResponse | null;
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
  status: DetailStatus;
}) {
  if (status === "idle") {
    return (
      <section className={styles.detail}>
        <EmptyState
          description="Выберите репозиторий слева."
          title="Карточка репозитория"
        />
      </section>
    );
  }
  if (status === "loading") {
    return (
      <section className={styles.detail}>
        <LoadingState label="Открываем карточку репозитория…" />
      </section>
    );
  }
  if (status === "error" || !detail) {
    return (
      <section className={styles.detail}>
        <ErrorState
          description={error ?? "Карточка репозитория недоступна."}
          title="Не удалось открыть репозиторий"
        />
      </section>
    );
  }

  const responsibilities = factsOfType(detail.facts, "responsibility");
  const interfaces = factsOfType(detail.facts, "interface_provided");
  const dependencies = factsOfType(detail.facts, "dependency_consumed");
  const deployments = factsOfType(detail.facts, "deployment_unit");
  const owners = factsOfType(detail.facts, "owner_candidate");

  return (
    <article className={styles.detail} aria-labelledby="repository-detail-title">
      <header className={styles.detailHeader}>
        <div>
          <span className="eyebrow">Репозиторий</span>
          <h2 id="repository-detail-title">{detail.repository.full_name}</h2>
          <p>
            {purposeSummary(detail.purpose) ??
              "Назначение пока не подтверждено доказательствами."}
          </p>
        </div>
        <div className={styles.detailBadges}>
          <span className="badge">
            {purposeRepositoryType(detail.purpose)}
          </span>
          {detail.repository.archived ? (
            <span className={styles.stale}>archived</span>
          ) : null}
        </div>
      </header>
      <dl className={styles.auditMeta}>
        <div>
          <dt>Последний аудит</dt>
          <dd>{formatDate(detail.latest_audit?.completed_at ?? null)}</dd>
        </div>
        <div>
          <dt>Уровень / покрытие</dt>
          <dd>
            {detail.latest_audit
              ? `${detail.latest_audit.audit_level} · ${detail.latest_audit.coverage_status}`
              : "Нет аудита"}
          </dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>
            {detail.latest_audit?.commit_sha?.slice(0, 12) ??
              detail.latest_audit?.metadata_snapshot_id ??
              "Недоступен"}
          </dd>
        </div>
      </dl>
      {detail.repository.source_url ? (
        <SourceLink url={detail.repository.source_url}>
          Открыть канонический репозиторий
        </SourceLink>
      ) : null}

      <FactSection
        facts={responsibilities}
        onEvidence={onEvidence}
        title="Обязанности"
      />
      <FactSection
        facts={interfaces}
        onEvidence={onEvidence}
        title="Интерфейсы"
      />
      <FactSection
        facts={dependencies}
        onEvidence={onEvidence}
        title="Зависимости"
      />
      <FactSection
        facts={deployments}
        onEvidence={onEvidence}
        title="Runtime и deployment"
      />
      <FactSection facts={owners} onEvidence={onEvidence} title="Владельцы" />
      <RelationshipSection
        onEvidence={onEvidence}
        relationships={detail.relationships}
      />
      <FindingSection findings={detail.findings} onEvidence={onEvidence} />
      <UnknownSection
        confirmations={detail.confirmation_queue}
        onEvidence={onEvidence}
        unknowns={detail.unknowns}
      />
      <ContradictionSection
        contradictions={detail.contradictions}
        onEvidence={onEvidence}
      />
      <CrossSourceSection
        crossSource={detail.cross_source}
        onEvidence={onEvidence}
      />
      <HistorySection history={history} />
      {detail.limitations.length > 0 ? (
        <details className={styles.disclosure}>
          <summary>Ограничения последнего аудита · {detail.limitations.length}</summary>
          <ul>
            {detail.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  );
}

function FactSection({
  facts,
  onEvidence,
  title
}: {
  facts: RepositoryFact[];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
  title: string;
}) {
  return (
    <details className={styles.disclosure} open={facts.length > 0}>
      <summary>
        {title} · {facts.length}
      </summary>
      {facts.length === 0 ? (
        <p className="muted">Доказанных данных пока нет.</p>
      ) : (
        <div className={styles.itemList}>
          {facts.map((fact) => (
            <section className={styles.item} key={fact.id}>
              <div className={styles.itemHeading}>
                <strong>{factSummary(fact)}</strong>
                <ClaimBadge
                  humanResolution={fact.human_resolution_status}
                  status={fact.claim_status}
                />
              </div>
              {factDetails(fact).map((detail) => (
                <p className="muted" key={detail}>
                  {detail}
                </p>
              ))}
              <EvidenceButtons
                evidence={fact.evidence}
                onEvidence={onEvidence}
                title={factSummary(fact)}
              />
            </section>
          ))}
        </div>
      )}
    </details>
  );
}

function RelationshipSection({
  onEvidence,
  relationships
}: {
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
  relationships: RepositoryDetailResponse["relationships"];
}) {
  return (
    <details className={styles.disclosure} open>
      <summary>Направленные связи · {relationships.length}</summary>
      <div className={styles.itemList}>
        {relationships.map((relationship) => {
          const label = `${relationship.from_repository.full_name} → ${
            relationship.to_repository?.full_name ??
            relationship.target_full_name
          }`;
          return (
            <section className={styles.item} key={relationship.id}>
              <div className={styles.itemHeading}>
                <strong>{label}</strong>
                <ClaimBadge
                  humanResolution={relationship.human_resolution_status}
                  status={relationship.claim_status}
                />
              </div>
              <span className={styles.relationshipType}>
                {relationship.relationship_type} · {relationship.direction}
              </span>
              {relationship.summary ? (
                <p className="muted">{relationship.summary}</p>
              ) : null}
              <EvidenceButtons
                evidence={relationship.evidence}
                onEvidence={onEvidence}
                title={label}
              />
            </section>
          );
        })}
      </div>
    </details>
  );
}

function FindingSection({
  findings,
  onEvidence
}: {
  findings: RepositoryDetailResponse["findings"];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
}) {
  return (
    <details className={styles.disclosure} open={findings.length > 0}>
      <summary>Риски и operability · {findings.length}</summary>
      <div className={styles.itemList}>
        {findings.map((finding) => (
          <section className={styles.item} key={finding.id}>
            <div className={styles.itemHeading}>
              <strong>{finding.title}</strong>
              <span
                className={`${styles.severity} ${
                  styles[`severity${capitalize(finding.severity)}`]
                }`}
              >
                {finding.severity} · {finding.status}
              </span>
            </div>
            <p>{finding.summary}</p>
            {finding.recommended_next_step ? (
              <p className="muted">{finding.recommended_next_step}</p>
            ) : null}
            <EvidenceButtons
              evidence={finding.evidence}
              onEvidence={onEvidence}
              title={finding.title}
            />
          </section>
        ))}
      </div>
    </details>
  );
}

function UnknownSection({
  confirmations,
  onEvidence,
  unknowns
}: {
  confirmations: RepositoryDetailResponse["confirmation_queue"];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
  unknowns: RepositoryFact[];
}) {
  return (
    <details
      className={styles.disclosure}
      open={unknowns.length + confirmations.length > 0}
    >
      <summary>
        Неизвестные и очередь подтверждения ·{" "}
        {unknowns.length + confirmations.length}
      </summary>
      <div className={styles.itemList}>
        {unknowns.map((unknown) => (
          <section className={styles.item} key={unknown.id}>
            <strong>{factSummary(unknown)}</strong>
            <p className="muted">
              Недостаточно доказательств — FounderOS не угадывает ответ.
            </p>
          </section>
        ))}
        {confirmations.map((confirmation) => (
          <section className={styles.item} key={`${confirmation.kind}-${confirmation.id}`}>
            <div className={styles.itemHeading}>
              <strong>{confirmation.label}</strong>
              <ClaimBadge
                humanResolution={confirmation.human_resolution_status}
                status={confirmation.claim_status}
              />
            </div>
            <p className="muted">
              Только очередь чтения: RI-007 не подтверждает и не отклоняет
              кандидатов.
            </p>
            <EvidenceButtons
              evidence={confirmation.evidence}
              onEvidence={onEvidence}
              title={confirmation.label}
            />
          </section>
        ))}
      </div>
    </details>
  );
}

function ContradictionSection({
  contradictions,
  onEvidence
}: {
  contradictions: RepositoryDetailResponse["contradictions"];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
}) {
  return (
    <details className={styles.disclosure} open={contradictions.length > 0}>
      <summary>Противоречия · {contradictions.length}</summary>
      <div className={styles.itemList}>
        {contradictions.map((contradiction) => (
          <section className={styles.item} key={contradiction.id}>
            <div className={styles.itemHeading}>
              <strong>{contradiction.summary}</strong>
              <span className={styles.stale}>{contradiction.status}</span>
            </div>
            <p className="muted">
              {contradiction.left_fact?.claim_id ?? "left"} ↔{" "}
              {contradiction.right_fact?.claim_id ?? "right"}
            </p>
            <EvidenceButtons
              evidence={contradiction.evidence}
              onEvidence={onEvidence}
              title={contradiction.summary}
            />
          </section>
        ))}
      </div>
    </details>
  );
}

function CrossSourceSection({
  crossSource,
  onEvidence
}: {
  crossSource: RepositoryDetailResponse["cross_source"];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
}) {
  const hasAttention =
    crossSource.summary.contradictions > 0 ||
    crossSource.summary.insufficient_evidence > 0 ||
    crossSource.summary.rejected_claim_sets > 0;
  return (
    <details className={styles.disclosure} open={hasAttention}>
      <summary>
        Между источниками · {crossSource.summary.comparisons}
      </summary>
      <p className="muted">
        Только exact structured claims: GitHub/Jira/Document → текущий RI факт.
        Free-text inference и fuzzy matching выключены.
      </p>
      <div className={styles.itemList}>
        {crossSource.comparisons.map((comparison) => {
          const evidence = [
            ...comparison.source_evidence,
            ...comparison.repository_evidence
          ];
          return (
            <section className={styles.item} key={comparison.id}>
              <div className={styles.itemHeading}>
                <strong>{comparison.summary}</strong>
                <CrossSourceStatus status={comparison.status} />
              </div>
              <p className="muted">{comparison.source_claim.summary}</p>
              <dl className="work-meta">
                <div>
                  <dt>Источник</dt>
                  <dd>
                    {comparison.source.provider} ·{" "}
                    {comparison.source.source_type} · {comparison.source.ref}
                  </dd>
                </div>
                <div>
                  <dt>Source claim</dt>
                  <dd>
                    {comparison.source_claim.claim_id}.
                    {comparison.source_claim.field} ={" "}
                    {comparison.source_claim.expected_value}
                  </dd>
                </div>
                <div>
                  <dt>RI fact</dt>
                  <dd>
                    {comparison.repository_fact?.actual_value ??
                      "insufficient evidence"}
                  </dd>
                </div>
              </dl>
              {comparison.source.url ? (
                <SourceLink url={comparison.source.url}>
                  Открыть связанный источник
                </SourceLink>
              ) : null}
              <EvidenceButtons
                evidence={evidence}
                onEvidence={onEvidence}
                title={comparison.summary}
              />
            </section>
          );
        })}
        {crossSource.comparisons.length === 0 ? (
          <p className="muted">
            Нет валидных structured claims для exact-сравнения.
          </p>
        ) : null}
      </div>
      {crossSource.rejected_claim_sets.length > 0 ? (
        <details className={styles.nestedDisclosure}>
          <summary>
            Отклонённые claim sets ·{" "}
            {crossSource.summary.rejected_claim_sets}
          </summary>
          <ul className="meta-list">
            {crossSource.rejected_claim_sets.map((rejected) => (
              <li
                key={`${rejected.source.record_id}-${rejected.error_code}`}
              >
                {rejected.source.provider}:{rejected.source.ref} —{" "}
                {rejected.error_code}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </details>
  );
}

function CrossSourceStatus({
  status
}: {
  status: RepositoryDetailResponse["cross_source"]["comparisons"][number]["status"];
}) {
  const className =
    status === "contradiction"
      ? styles.crossSourceContradiction
      : status === "agreement"
        ? styles.observed
        : styles.candidate;
  return (
    <span className={`${styles.claimBadge} ${className}`}>{status}</span>
  );
}

function HistorySection({
  history
}: {
  history: RepositoryHistoryResponse | null;
}) {
  return (
    <details className={styles.disclosure}>
      <summary>История аудита · {history?.runs.length ?? 0}</summary>
      <div className={styles.itemList}>
        {history?.runs.map((run) => (
          <section className={styles.item} key={run.id}>
            <div className={styles.itemHeading}>
              <strong>
                {run.audit_level} · {run.coverage_status}
              </strong>
              <span className="badge">{run.status}</span>
            </div>
            <p className="muted">
              {formatDate(run.completed_at)} · {run.engine_version} ·{" "}
              {run.commit_sha?.slice(0, 12) ??
                run.metadata_snapshot_id ??
                "target unavailable"}
            </p>
            <p className="muted">
              Проверки: {run.completed_checks.join(", ") || "нет"} · artifacts:{" "}
              {run.artifact_count} ({run.artifact_status})
            </p>
          </section>
        ))}
      </div>
    </details>
  );
}

export function RelationshipGraph({
  graph
}: {
  graph: RepositoryGraphResponse | null;
}) {
  if (!graph) {
    return <LoadingState label="Загружаем граф связей…" />;
  }
  return (
    <section className={styles.graph} aria-label="Направленный граф репозиториев">
      <div className={styles.graphLegend}>
        <span className={styles.observed}>observed</span>
        <span className={styles.inferred}>inferred</span>
        <span className={styles.confirmed}>human confirmed</span>
        <span className={styles.candidate}>unresolved candidate</span>
      </div>
      {graph.edges.length === 0 ? (
        <EmptyState
          description="В сохранённых RI-006 данных пока нет текущих направленных связей."
          title="Связи не найдены"
        />
      ) : (
        <div className={styles.edgeList}>
          {graph.edges.map((edge) => (
            <GraphEdge edge={edge} key={edge.id} />
          ))}
        </div>
      )}
    </section>
  );
}

function GraphEdge({ edge }: { edge: RepositoryGraphEdge }) {
  const state =
    edge.human_resolution_status === "confirmed"
      ? "confirmed"
      : edge.resolution_status === "candidate"
        ? "candidate"
        : edge.claim_status;
  return (
    <article className={`${styles.edge} ${styles[state]}`}>
      <div>
        <strong>{edge.from_repository_full_name}</strong>
        <span aria-hidden="true"> → </span>
        <strong>{edge.target_full_name}</strong>
      </div>
      <span>{edge.relationship_type}</span>
      <small>
        {state} · confidence {Math.round(edge.confidence * 100)}%
      </small>
      {edge.summary ? <p>{edge.summary}</p> : null}
    </article>
  );
}

function ClaimBadge({
  humanResolution,
  status
}: {
  humanResolution: string;
  status: string;
}) {
  const label =
    humanResolution === "confirmed"
      ? "confirmed"
      : humanResolution === "rejected"
        ? "rejected"
        : status;
  const className =
    label === "confirmed"
      ? styles.confirmed
      : label === "inferred"
        ? styles.inferred
        : label === "observed"
          ? styles.observed
          : styles.candidate;
  return <span className={`${styles.claimBadge} ${className}`}>{label}</span>;
}

function EvidenceButtons({
  evidence,
  onEvidence,
  title
}: {
  evidence: RepositoryEvidence[];
  onEvidence: (evidence: RepositoryEvidence, title: string) => void;
  title: string;
}) {
  if (evidence.length === 0) {
    return <span className="muted">Evidence: нет</span>;
  }
  return (
    <div
      aria-label={`Evidence: ${title}`}
      className={styles.evidenceButtons}
      role="group"
    >
      {evidence.map((item, index) => (
        <button
          className="button secondary"
          key={`${item.id}-${item.role}`}
          onClick={() => onEvidence(item, title)}
          type="button"
        >
          Источник {index + 1} · {item.role}
        </button>
      ))}
    </div>
  );
}

function RepositoryEvidenceDrawer({
  onClose,
  selected
}: {
  onClose: () => void;
  selected: { evidence: RepositoryEvidence; title: string } | null;
}) {
  return (
    <div className={styles.evidenceColumn}>
      <EvidenceDrawer
        evidence={
          selected
            ? {
                kind: selected.evidence.kind,
                source: selected.evidence.source,
                ref: selected.evidence.ref ?? "",
                url: selected.evidence.url
              }
            : null
        }
        itemTitle={selected?.title ?? null}
        onClose={selected ? onClose : undefined}
        selectionDescription={
          selected
            ? `Роль: ${selected.evidence.role}. Raw source body не возвращается.`
            : null
        }
        selectionMode={selected ? "manual" : null}
      />
    </div>
  );
}

export function filterRepositoryPortfolio(
  repositories: RepositoryPortfolioItem[],
  filters: PortfolioFilters
): RepositoryPortfolioItem[] {
  const query = filters.query.trim().toLocaleLowerCase("ru-RU");
  return repositories.filter((repository) => {
    const searchable = [
      repository.full_name,
      repository.purpose_summary ?? "",
      repository.operational_summary ?? "",
      ...repository.product_candidates,
      ...repository.owner_candidates
    ]
      .join(" ")
      .toLocaleLowerCase("ru-RU");
    if (query && !searchable.includes(query)) {
      return false;
    }
    if (
      filters.repositoryType !== "all" &&
      repository.repository_type !== filters.repositoryType
    ) {
      return false;
    }
    if (
      filters.product !== "all" &&
      !repository.product_candidates.includes(filters.product)
    ) {
      return false;
    }
    if (filters.owner === "confirmed" && !repository.has_confirmed_owner) {
      return false;
    }
    if (
      filters.owner === "unresolved" &&
      repository.has_confirmed_owner
    ) {
      return false;
    }
    if (filters.lifecycle === "active" && repository.archived) {
      return false;
    }
    if (filters.lifecycle === "archived" && !repository.archived) {
      return false;
    }
    if (
      filters.severity !== "all" &&
      repository.open_findings[filters.severity] === 0
    ) {
      return false;
    }
    if (filters.staleness === "stale" && !repository.has_stale_intelligence) {
      return false;
    }
    if (filters.staleness === "fresh" && repository.has_stale_intelligence) {
      return false;
    }
    return true;
  });
}

function factsOfType(
  facts: RepositoryFact[],
  factType: string
): RepositoryFact[] {
  return facts.filter((fact) => fact.fact_type === factType);
}

function purposeSummary(fact: RepositoryFact | null): string | null {
  return fact && typeof fact.value.summary === "string"
    ? fact.value.summary
    : null;
}

function purposeRepositoryType(fact: RepositoryFact | null): string {
  return fact && typeof fact.value.repository_type === "string"
    ? fact.value.repository_type
    : "unknown";
}

function factSummary(fact: RepositoryFact): string {
  for (const key of ["summary", "question", "repository_type"]) {
    const value = fact.value[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return fact.claim_id;
}

function factDetails(fact: RepositoryFact): string[] {
  const value = fact.value.details;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((left, right) =>
    left.localeCompare(right)
  );
}

function formatDate(value: string | null): string {
  if (!value) {
    return "Неизвестно";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Неизвестно"
    : new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
