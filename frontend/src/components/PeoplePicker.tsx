import { Select } from "./ui/Field";

/**
 * Pick one or more people for a task. The first row is always shown, and
 * "Add another person" adds a row. Empty rows are dropped when saving.
 */
export function PeoplePicker({
  people,
  value,
  onChange,
  label = "Assigned to",
  hint,
  error,
  emptyLabel = "Nobody",
}: {
  people: { id: string; name: string }[];
  value: string[];
  onChange: (next: string[]) => void;
  label?: string;
  hint?: string;
  error?: string | null;
  emptyLabel?: string;
}) {
  const rows = value.length ? value : [""];
  const set = (i: number, id: string) => onChange(rows.map((v, j) => (j === i ? id : v)));
  const remove = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const canAdd = rows.every(Boolean) && rows.length < people.length;

  return (
    <div className="people-picker">
      {rows.map((current, i) => (
        <div className="people-picker-row" key={i}>
          <Select
            label={i === 0 ? label : `Person ${i + 1}`}
            hint={i === 0 ? hint : undefined}
            error={i === rows.length - 1 ? error ?? undefined : undefined}
            value={current}
            onChange={(e) => set(i, e.target.value)}
            placeholder={i === 0 ? emptyLabel : "Pick a person"}
            // A person already picked in another row is not offered again.
            options={people
              .filter((p) => p.id === current || !rows.includes(p.id))
              .map((p) => ({ value: p.id, label: p.name }))}
          />
          {rows.length > 1 && (
            <button
              type="button"
              className="text-button people-picker-remove"
              onClick={() => remove(i)}
              aria-label={`Remove ${people.find((p) => p.id === current)?.name ?? `person ${i + 1}`}`}
            >
              Remove
            </button>
          )}
        </div>
      ))}
      {canAdd && (
        <button type="button" className="text-button strong-link" onClick={() => onChange([...rows, ""])}>
          Add another person
        </button>
      )}
    </div>
  );
}
