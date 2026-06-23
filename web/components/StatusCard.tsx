type StatusCardProps = {
  title: string;
  value: string;
  description: string;
};

export function StatusCard({ title, value, description }: StatusCardProps) {
  return (
    <section className="status-card">
      <span className="status-card-title">{title}</span>
      <strong className="status-card-value">{value}</strong>
      <p className="status-card-description">{description}</p>
    </section>
  );
}
