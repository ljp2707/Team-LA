import { useState } from "react";
import { deleteTask, getTask } from "../api/tasks";
import { useApi } from "../hooks/useApi";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { LoadingState } from "./ui/States";

/**
 * Admins only: confirm before deleting a task. Names the task, lists the tasks that
 * wait on it (they stop waiting), and says it cannot be undone.
 */
export function DeleteTaskDialog({
  open,
  taskId,
  taskName,
  onClose,
  onDeleted,
}: {
  open: boolean;
  taskId: string;
  taskName: string;
  onClose: () => void;
  onDeleted: (name: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Loaded when the dialog opens, so the list of waiting tasks is current.
  const task = useApi(() => (open ? getTask(taskId) : Promise.resolve(null)), [open, taskId]);
  // Ignore what an earlier opening loaded for a different task.
  const loaded = task.data?.id === taskId ? task.data : null;
  const waiting = loaded?.waiting_on_this ?? [];

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await deleteTask(taskId);
      onDeleted(taskName);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={`Delete ${taskName}?`}
      onClose={() => {
        setError(null);
        onClose();
      }}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => void confirm()} disabled={busy || !loaded}>
            {busy ? "Deleting" : "Delete task"}
          </Button>
        </>
      }
    >
      {!loaded && !task.error ? (
        <LoadingState label="Checking what waits on this task" />
      ) : (
        <>
          <p>
            This permanently deletes <strong>{taskName}</strong> and its reminders. <strong>This cannot be undone.</strong>
          </p>
          {waiting.length > 0 && (
            <div className="note-box" role="note">
              <p>
                {waiting.length === 1 ? "This task waits on it" : "These tasks wait on it"}. They will no longer wait on it:
              </p>
              <ul className="plain-list">
                {waiting.map((w) => (
                  <li key={w.id}>{w.name}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="muted small">
            The history keeps a note that it was deleted and by whom. Its notes stay in the history, and its links and
            files move to the program&apos;s Links and files. To keep the task but stop working on it, skip it instead.
          </p>
        </>
      )}
      {(error || task.error) && (
        <p className="field-error" role="alert">
          {error ?? task.error?.message}
        </p>
      )}
    </Dialog>
  );
}
