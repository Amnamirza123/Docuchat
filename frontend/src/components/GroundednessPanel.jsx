export default function GroundednessPanel({ data }) {
  if (!data) {
    return (
      <aside className="sidebar sidebar-right">
        <h3>Grounding</h3>
        <p className="panel-empty">Send a message to see grounding details here.</p>
      </aside>
    );
  }

  const { grounded, score } = data;
  const citations = Array.isArray(data.citations)
    ? data.citations
    : JSON.parse(data.citations || "[]");

  return (
    <aside className="sidebar sidebar-right">
      <h3>Grounding</h3>

      {grounded ? (
        <>
          <div className="groundedness-score">
            <span className="score-label">Groundedness Score</span>
            <span className="score-value">{Math.round(score * 100)}%</span>
          </div>

          <div className="citations-section">
            <h4>Citations</h4>
            <ul className="citation-list">
              {citations.map((c, i) => (
                <li key={i} className="citation-item">
                  <span className="citation-doc">{c.filename}</span>
                  {c.page_number != null && (
                    <span className="citation-page">p.{c.page_number}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : (
        <p className="panel-empty">
          General conversation — no documents referenced for this response.
        </p>
      )}
    </aside>
  );
}