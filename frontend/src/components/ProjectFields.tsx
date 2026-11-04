import type { ProjectEdit } from "../api/types";
import { DateInput, Select, TextArea, TextInput } from "./ui/Field";

export type DetailsDraft = Omit<ProjectEdit, "site_id" | "day_one"> & { site_id?: string | null; day_one?: string | null };

interface ProjectFieldsProps {
  value: DetailsDraft;
  onChange: (change: Partial<DetailsDraft>) => void;
  siteTypes: string[];
  instructors: { id: string; name: string }[];
  partners: { id: string; name: string }[];
  errors?: Partial<Record<keyof DetailsDraft, string>>;
}

/**
 * The launch details used on New Project and in Edit details:
 * hours, location, instructors, partner contact, shipping and the Drive folder.
 * Site and Day 1 are handled by each page, since they work differently there.
 */
export function ProjectFields({ value, onChange, siteTypes, instructors, partners, errors = {} }: ProjectFieldsProps) {
  function toggle(list: "instructor_ids" | "partner_ids", id: string) {
    const current = value[list];
    onChange({ [list]: current.includes(id) ? current.filter((x) => x !== id) : [...current, id] });
  }

  return (
    <>
      <div className="form-grid">
        <Select
          label="Site type"
          value={value.site_type ?? ""}
          onChange={(e) => onChange({ site_type: e.target.value || null })}
          placeholder="Choose a site type"
          options={siteTypes.map((t) => ({ value: t, label: t }))}
        />
        <DateInput
          label="Last day (optional)"
          hint="Leave blank to use the template's length."
          value={value.end_date ?? ""}
          onChange={(e) => onChange({ end_date: e.target.value || null })}
          error={errors.end_date}
        />
        <TextInput
          label="Program hours"
          placeholder="Sun 10:00 to 12:00"
          value={value.program_hours}
          onChange={(e) => onChange({ program_hours: e.target.value })}
          maxLength={200}
        />
        <TextInput
          label="Location"
          placeholder="City, WA"
          value={value.location}
          onChange={(e) => onChange({ location: e.target.value })}
          maxLength={200}
        />
      </div>

      <fieldset className="check-group">
        <legend>Lead instructors</legend>
        {instructors.length === 0 ? (
          <p className="muted small">No instructors in Airtable yet.</p>
        ) : (
          instructors.map((person) => (
            <label key={person.id} className="check-option">
              <input
                type="checkbox"
                checked={value.instructor_ids.includes(person.id)}
                onChange={() => toggle("instructor_ids", person.id)}
              />
              {person.name}
            </label>
          ))
        )}
      </fieldset>

      <div className="form-grid">
        <TextInput
          label="Partner contact name"
          value={value.partner_name}
          onChange={(e) => onChange({ partner_name: e.target.value })}
          maxLength={200}
        />
        <TextInput
          label="Partner email"
          type="email"
          value={value.partner_email}
          onChange={(e) => onChange({ partner_email: e.target.value })}
          error={errors.partner_email}
          maxLength={200}
        />
        <TextInput
          label="Partner phone"
          type="tel"
          value={value.partner_phone}
          onChange={(e) => onChange({ partner_phone: e.target.value })}
          maxLength={50}
        />
      </div>
      <TextArea
        label="Shipping address"
        rows={2}
        value={value.shipping_address}
        onChange={(e) => onChange({ shipping_address: e.target.value })}
        maxLength={1000}
      />
      <TextInput
        label="Google Drive folder"
        type="url"
        placeholder="https://drive.google.com/..."
        value={value.drive_folder}
        onChange={(e) => onChange({ drive_folder: e.target.value })}
        error={errors.drive_folder}
        maxLength={1000}
      />

      {partners.length > 0 && (
        <fieldset className="check-group">
          <legend>Partner access</legend>
          <p className="muted small">Partners can see this launch and update the tasks assigned to them.</p>
          {partners.map((person) => (
            <label key={person.id} className="check-option">
              <input
                type="checkbox"
                checked={value.partner_ids.includes(person.id)}
                onChange={() => toggle("partner_ids", person.id)}
              />
              {person.name}
            </label>
          ))}
        </fieldset>
      )}
    </>
  );
}

/** Checks the form before it goes to the server, with the same rules the server uses. */
export function checkDetails(value: DetailsDraft): Partial<Record<keyof DetailsDraft, string>> {
  const errors: Partial<Record<keyof DetailsDraft, string>> = {};
  const drive = value.drive_folder.trim();
  if (drive && !drive.startsWith("https://drive.google.com/")) {
    errors.drive_folder = "Use a Google Drive link that starts with https://drive.google.com/";
  }
  const email = value.partner_email.trim();
  if (email && (!email.includes("@") || email.includes(" "))) {
    errors.partner_email = "That email does not look right.";
  }
  if (value.end_date && value.day_one && value.end_date < value.day_one) {
    errors.end_date = "The last day must be on or after Day 1.";
  }
  return errors;
}
