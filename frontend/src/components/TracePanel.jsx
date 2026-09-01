export default function TracePanel({ trace }) {
  if (!trace || trace.length === 0) return null;
  return (
    <div className="trace-panel">
      <span className="trace-label">nodes fired:</span>
      {trace.map((node, i) => (
        <span key={i} className="trace-node">
          {node}
          {i < trace.length - 1 && <span className="trace-arrow">→</span>}
        </span>
      ))}
    </div>
  );
}
