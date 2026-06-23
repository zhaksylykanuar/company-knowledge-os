type ErrorStateProps = {
  title: string;
  description: string;
};

export function ErrorState({ title, description }: ErrorStateProps) {
  return (
    <section className="state error">
      <strong>{title}</strong>
      <p>{description}</p>
    </section>
  );
}
