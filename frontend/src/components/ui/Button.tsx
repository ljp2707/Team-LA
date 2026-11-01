import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface ButtonProps {
  children: ReactNode;
  variant?: "primary" | "dark" | "light";
  /** A path inside the app. Renders a router link. */
  to?: string;
  /** A full page address such as /auth/login. Renders a plain link. */
  href?: string;
  type?: "button" | "submit";
  onClick?: () => void;
}

export function Button({
  children,
  variant = "primary",
  to,
  href,
  type = "button",
  onClick,
}: ButtonProps) {
  const className = `button button--${variant}`;
  if (to) {
    return (
      <Link className={className} to={to}>
        {children}
      </Link>
    );
  }
  if (href) {
    return (
      <a className={className} href={href}>
        {children}
      </a>
    );
  }
  return (
    <button className={className} type={type} onClick={onClick}>
      {children}
    </button>
  );
}
