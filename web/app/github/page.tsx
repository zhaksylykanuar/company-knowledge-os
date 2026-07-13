import { EmptyState } from "../../components/EmptyState";
import { GitHubProductConnectPanel } from "../../components/GitHubProductConnectPanel";
import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { M } from "../../lib/messages";

export default function GitHubPage() {
  return (
    <>
      <PageHeader
        eyebrow={M.githubPage.eyebrow}
        title={M.githubPage.title}
        description={M.githubPage.description}
      />
      <GitHubProductConnectPanel />
      <section className="grid">
        <StatusCard
          description={M.githubPage.connectionDescription}
          title={M.githubPage.connectionTitle}
          value={M.githubPage.connectionValue}
        />
        <StatusCard
          description={M.githubPage.reposDescription}
          title={M.githubPage.reposTitle}
          value={M.githubPage.reposValue}
        />
        <StatusCard
          description={M.githubPage.syncJobsDescription}
          title={M.githubPage.syncJobsTitle}
          value={M.githubPage.syncJobsValue}
        />
        <StatusCard
          description={M.githubPage.normalizationDescription}
          title={M.githubPage.normalizationTitle}
          value={M.githubPage.normalizationValue}
        />
      </section>
      <EmptyState
        description={M.githubPage.scaffoldDescription}
        title={M.githubPage.scaffoldTitle}
      />
    </>
  );
}
