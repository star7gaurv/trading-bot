/**
 * Compact table. Pass columns + rows. Built on raw <table> with our base.css styles.
 * Props:
 *   columns: [{ key, label, align?, format?, render?, width? }]
 *   rows: array of objects
 *   emptyMessage?: string
 *   loading?: boolean
 *   onRowClick?: (row) => void
 *   maxHeight?: string (e.g. '480px') — scrollable body with sticky header
 */
export default function Table({
  columns,
  rows,
  emptyMessage = "No data",
  loading = false,
  onRowClick,
  maxHeight,
}) {
  const containerStyle = {
    ...(maxHeight ? { maxHeight, overflowY: "auto" } : {}),
    overflowX: "auto",
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-text-tertiary text-xs">Loading…</div>
    );
  }
  if (!rows || rows.length === 0) {
    return (
      <div className="p-6 text-center text-text-tertiary text-xs">{emptyMessage}</div>
    );
  }

  return (
    <div style={containerStyle} className="w-full">
      <table className="min-w-full">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={{
                  textAlign: c.align || "left",
                  width: c.width,
                }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.id ?? row.key ?? i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? "cursor-pointer" : ""}
            >
              {columns.map((c) => {
                const raw = row[c.key];
                const cell = c.render
                  ? c.render(row)
                  : c.format
                  ? c.format(raw, row)
                  : raw ?? "—";
                return (
                  <td
                    key={c.key}
                    style={{
                      textAlign: c.align || "left",
                      fontFamily: c.mono ? "JetBrains Mono, monospace" : undefined,
                    }}
                  >
                    {cell}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
