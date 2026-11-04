import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";

const MESSAGES: Record<string, { title: string; text: string }> = {
  google: {
    title: "Google did not finish signing you in",
    text: "Google could not confirm your account. Please try signing in again.",
  },
  domain: {
    title: "That account is not allowed here",
    text: "NMU Launches only accepts Google accounts from your organization's domain. Try a different account.",
  },
  airtable: {
    title: "We could not check your account",
    text: "NMU Launches could not reach its records just now. Please try again in a minute.",
  },
  "not-configured": {
    title: "Google sign in is not set up yet",
    text: "An admin needs to add the Google client ID and secret to the backend settings. The README explains how.",
  },
};

export function NotAuthorized() {
  const [params] = useSearchParams();
  const reason = params.get("reason") ?? "";
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (reason) return;
    api<{ email: string | null }>("/auth/denied")
      .then((result) => setEmail(result.email))
      .catch(() => setEmail(null));
  }, [reason]);

  const known = MESSAGES[reason];
  const title = known?.title ?? "You do not have access yet";
  const text =
    known?.text ??
    (email
      ? `${email} is not on the NMU Launches list. Ask an admin to add you, or sign in with the account they added.`
      : "Your Google account is not on the NMU Launches list. Ask an admin to add you, or sign in with the account they added.");

  return (
    <main className="standalone">
      <section className="card">
        <h1>{title}</h1>
        <p>{text}</p>
        <div className="card-actions">
          {reason !== "not-configured" && reason !== "airtable" && (
            <Button href="/auth/login" variant="dark">
              Use a different account
            </Button>
          )}
          {reason === "airtable" && (
            <Button href="/auth/login" variant="dark">
              Try again
            </Button>
          )}
          <Button to="/" variant="outline">
            Back to the home page
          </Button>
        </div>
      </section>
    </main>
  );
}
