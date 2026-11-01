import { Card } from "./Card";

/** The card on every placeholder page, listing what the page will do. */
export function ComingSoon({ features }: { features: string[] }) {
  return (
    <Card className="coming-soon">
      <h2>Coming soon</h2>
      <p>This page will have:</p>
      <ul>
        {features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>
    </Card>
  );
}
