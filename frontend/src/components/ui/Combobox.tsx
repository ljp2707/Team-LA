import { useEffect, useId, useMemo, useRef, useState } from "react";

export interface ComboOption {
  value: string;
  label: string;
  detail?: string;
}

interface ComboboxProps {
  label: string;
  options: ComboOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  hint?: string;
  error?: string | null;
  /** An extra choice at the end of the list, such as "Add a new site". */
  extra?: { label: string; onSelect: (typed: string) => void };
}

/** A searchable select. Type to filter, arrow keys to move, Enter to pick. */
export function Combobox({ label, options, value, onChange, placeholder, hint, error, extra }: ComboboxProps) {
  const id = useId();
  const listId = `${id}-list`;
  const hintId = `${id}-hint`;
  const selected = options.find((o) => o.value === value) ?? null;
  const [text, setText] = useState(selected?.label ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapper = useRef<HTMLDivElement>(null);

  const selectedLabel = selected?.label ?? "";
  useEffect(() => {
    if (!open) setText(selectedLabel);
  }, [selectedLabel, open]);

  useEffect(() => {
    function close(event: MouseEvent) {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const filtered = useMemo(() => {
    const wanted = text.trim().toLowerCase();
    if (!wanted || wanted === selected?.label.toLowerCase()) return options;
    return options.filter((o) => `${o.label} ${o.detail ?? ""}`.toLowerCase().includes(wanted));
  }, [options, text, selected]);

  const count = filtered.length + (extra ? 1 : 0);

  function pick(index: number) {
    if (index < filtered.length) {
      onChange(filtered[index].value);
      setText(filtered[index].label);
    } else if (extra) {
      extra.onSelect(text.trim() === selected?.label ? "" : text.trim());
    }
    setOpen(false);
  }

  return (
    <div className="field combobox" ref={wrapper}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className="input select"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && count ? `${id}-option-${active}` : undefined}
        aria-describedby={hint || error ? hintId : undefined}
        aria-invalid={error ? true : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          setActive(0);
          if (!event.target.value) onChange(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, count - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (event.key === "Enter" && open && count) {
            event.preventDefault();
            pick(active);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && (
        <ul className="combo-list" id={listId} role="listbox" aria-label={label}>
          {filtered.map((option, index) => (
            <li
              key={option.value}
              id={`${id}-option-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "is-active" : undefined}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(index)}
            >
              <span>{option.label}</span>
              {option.detail && <span className="muted small">{option.detail}</span>}
            </li>
          ))}
          {!filtered.length && !extra && <li className="muted combo-empty">No matches</li>}
          {extra && (
            <li
              id={`${id}-option-${filtered.length}`}
              role="option"
              aria-selected={false}
              className={`combo-extra${active === filtered.length ? " is-active" : ""}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(filtered.length)}
            >
              {extra.label}
            </li>
          )}
        </ul>
      )}
      {(hint || error) && (
        <span id={hintId} className={error ? "field-error" : "field-hint"}>
          {error || hint}
        </span>
      )}
    </div>
  );
}
