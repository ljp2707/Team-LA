import { get, query, send, upload } from "./client";
import type { MyReminder, MyTasks, Note, ReminderPanel, TaskDetail, TaskRow, TaskStatus } from "./types";

export const myTasks = (params: { filter?: string; project?: string } = {}) =>
  get<MyTasks>(`/api/tasks/mine${query(params)}`);

export const getTask = (id: string) => get<TaskDetail>(`/api/tasks/${id}`);

export const setStatus = (id: string, status: TaskStatus) =>
  send<TaskRow>("PATCH", `/api/tasks/${id}`, { status });

export const updateTask = (
  id: string,
  body: { due_date?: string; name?: string; depends_on?: string[] },
) => send<TaskRow>("PATCH", `/api/tasks/${id}`, body);

/** Sets everyone on the task. An empty list leaves it with nobody. */
export const assignTask = (id: string, userIds: string[]) =>
  send<TaskRow>("POST", `/api/tasks/${id}/assign`, { user_ids: userIds });

export const addNote = (id: string, text: string) =>
  send<{ notes: Note[] }>("POST", `/api/tasks/${id}/notes`, { text });

export const deleteNote = (id: string) => send<{ deleted: boolean }>("DELETE", `/api/notes/${id}`);

export const shareNote = (id: string, visibility: "Internal" | "Shared") =>
  send<Note>("PATCH", `/api/notes/${id}`, { visibility });

export const addTaskLink = (id: string, title: string, url: string) =>
  send<{ id: string; kind: string }>("POST", `/api/tasks/${id}/links`, { title, url });

export const addTaskFile = (id: string, file: File, title: string) =>
  upload<{ id: string; kind: string }>(`/api/tasks/${id}/files`, file, { title });

export const addReminder = (id: string, sendOn: string, note: string) =>
  send<ReminderPanel>("POST", `/api/tasks/${id}/reminders`, { send_on: sendOn, note });

export const cancelReminder = (id: string) =>
  send<{ cancelled: boolean }>("DELETE", `/api/reminders/${id}`);

export const myReminders = () => get<{ reminders: MyReminder[] }>("/api/reminders/mine");
