import { useState } from "react";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { Field, TextInput } from "./ui/Field";

// Keep these in step with ALLOWED_FILE_TYPES and MAX_FILE_BYTES in
// backend/app/services/links.py. The backend checks again, and its rules count.
const ACCEPT = ".jpg,.jpeg,.png,.gif,.webp,.heic,.heif,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv";
const MAX_MB = 5;

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

/** "2.4 MB" or "640 KB", for showing a file's size. */
export function fileSize(bytes: number | null | undefined): string {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Upload a file or photo from the person's computer to a task or a launch. */
export function FileDialog({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (file: File, title: string) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  function reset() {
    setFile(null);
    setTitle("");
    setError(null);
    setInputKey((key) => key + 1); // Clears the file input
  }

  function choose(picked: File | null) {
    setError(null);
    if (picked && picked.size > MAX_MB * 1024 * 1024) {
      setFile(null);
      setInputKey((key) => key + 1);
      setError(`Files can be up to ${MAX_MB} MB. Put bigger files in Google Drive and attach a link.`);
      return;
    }
    setFile(picked);
  }

  async function save() {
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(file, title.trim());
      reset();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Upload a file"
      description={`Photos, PDFs, Word, Excel, PowerPoint, text or CSV files, up to ${MAX_MB} MB.`}
      onClose={() => {
        reset();
        onClose();
      }}
      actions={
        <>
          <Button
            variant="outline"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="file-form" disabled={busy || !file}>
            {busy ? "Uploading" : "Upload file"}
          </Button>
        </>
      }
    >
      <form
        id="file-form"
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <Field
          label="File"
          error={error}
          hint={file ? `${file.name} · ${fileSize(file.size)}` : undefined}
        >
          {(ids) => (
            <input
              key={inputKey}
              className="input"
              type="file"
              accept={ACCEPT}
              required
              onChange={(e) => choose(e.target.files?.[0] ?? null)}
              {...ids}
            />
          )}
        </Field>
        <TextInput
          label="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          placeholder={file?.name ?? "Pool deck photo"}
          hint="Leave blank to use the file's name."
        />
      </form>
    </Dialog>
  );
}
