import { useId } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
  className?: string;
}

/** A label, the control, and an optional hint or error tied to it. */
export function Field({ label, hint, error, children, className = "" }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const describedBy = error || hint ? hintId : undefined;
  return (
    <div className={`field ${className}`.trim()}>
      <label htmlFor={id}>{label}</label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {(error || hint) && (
        <span id={hintId} className={error ? "field-error" : "field-hint"}>
          {error || hint}
        </span>
      )}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string | null };

export function TextInput({ label, hint, error, className, ...rest }: InputProps) {
  return (
    <Field label={label} hint={hint} error={error} className={className}>
      {(ids) => <input className="input" {...ids} {...rest} />}
    </Field>
  );
}

/** A date picker. The value is YYYY-MM-DD. */
export function DateInput(props: InputProps) {
  return <TextInput type="date" {...props} />;
}

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null };

export function TextArea({ label, hint, error, className, ...rest }: TextAreaProps) {
  return (
    <Field label={label} hint={hint} error={error} className={className}>
      {(ids) => <textarea className="input textarea" {...ids} {...rest} />}
    </Field>
  );
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  hint?: string;
  error?: string | null;
  options: { value: string; label: string }[];
  placeholder?: string;
};

export function Select({ label, hint, error, options, placeholder, className, ...rest }: SelectProps) {
  return (
    <Field label={label} hint={hint} error={error} className={className}>
      {(ids) => (
        <select className="input select" {...ids} {...rest}>
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}
