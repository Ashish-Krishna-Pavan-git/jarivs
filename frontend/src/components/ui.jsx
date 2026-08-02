import { Button as Btn } from "./Button";
export { Btn as Button };

export const Field = ({ label, children }) => (
  <label className="field">
    <span>{label}</span>
    {children}
  </label>
);

export const Metric = ({ icon: Icon, label, value }) => (
  <article className="metric">
    {Icon && <Icon size={18} />}
    <span>{label}</span>
    <strong>{value ?? "-"}</strong>
  </article>
);

export const Header = ({ eyebrow, title, actions }) => (
  <header className="top">
    <div>
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
    </div>
    <div className="actions">{actions}</div>
  </header>
);

export function Table({ rows, columns, empty = "No records" }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.label}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((r, i) => (
              <tr key={r.id || i}>
                {columns.map((c) => (
                  <td key={c.label}>{c.render ? c.render(r) : String(r[c.key] ?? "")}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length}>{empty}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}