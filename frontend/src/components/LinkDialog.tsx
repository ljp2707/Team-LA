import { useState } from "react";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { TextInput } from "./ui/Field";

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

/** Attach a Drive, Docs or Canva link to a task or a launch. */
export function LinkDialog({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (title: string, url: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!url.trim().startsWith("https://")) {
      setError("Use a link that starts with https://");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(title.trim() || url.trim(), url.trim());
      setTitle("");
      setUrl("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Attach a link"
      description="Google Drive, Docs, Sheets or Canva links work best."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="link-form" disabled={busy}>
            {busy ? "Saving" : "Attach link"}
          </Button>
        </>
      }
    >
      <form
        id="link-form"
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Equipment packing list" />
        <TextInput label="Link" type="url" value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://drive.google.com/..." error={error} />
      </form>
    </Dialog>
  );
}

