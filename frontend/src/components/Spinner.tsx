export default function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="spinner-wrap">
      <div className="spinner" aria-label={label} />
      <p className="spinner-label">{label}</p>
    </div>
  );
}
