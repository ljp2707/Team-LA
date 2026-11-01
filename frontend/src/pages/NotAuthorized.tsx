import { useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/Button";

const MESSAGES: Record<string, string> = {
  google: "Google could not confirm your account. Please try signing in again.",
  domain: "That Google account is not on the NMU domain. Use your NMU Google account.",
  airtable: "We could not check your account just now. Please try again in a minute.",
};

export function NotAuthorized() {
  const [params] = useSearchParams();
  const reason = params.get("reason") ?? "";

  return (
    <main className="standalone">
      <section className="card">
        <h1>You do not have access yet</h1>
        <p>{MESSAGES[reason] ?? "Ask an admin to add you."}</p>
        <Button to="/" variant="dark">
          Back to sign in
        </Button>
      </section>
    </main>
  );
}
