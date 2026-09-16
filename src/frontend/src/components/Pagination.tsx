export const PAGE_SIZE = 5;

export default function Pagination({
  page,
  totalItems,
  onChange,
  pageSize = PAGE_SIZE,
}: {
  page: number;
  totalItems: number;
  onChange: (page: number) => void;
  pageSize?: number;
}) {
  if (totalItems === 0) return null;

  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(Math.max(page, 1), totalPages);
  const first = (safePage - 1) * pageSize + 1;
  const last = Math.min(safePage * pageSize, totalItems);

  return (
    <div className="table-pagination">
      <span>{first}–{last} of {totalItems}</span>
      <div>
        <button type="button" onClick={() => onChange(safePage - 1)} disabled={safePage === 1} aria-label="Previous page">‹</button>
        <span>Page {safePage} of {totalPages}</span>
        <button type="button" onClick={() => onChange(safePage + 1)} disabled={safePage === totalPages} aria-label="Next page">›</button>
      </div>
    </div>
  );
}
