type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <section className="state">
      <strong>{title}</strong>
      <p>{description}</p>
    </section>
  );
}
