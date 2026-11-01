import { Button } from "../components/ui/Button";

export function NotFound() {
  return (
    <main className="standalone">
      <section className="card">
        <h1>Page not found</h1>
        <p>That page does not exist.</p>
        <Button to="/" variant="dark">
          Go home
        </Button>
      </section>
    </main>
  );
}
