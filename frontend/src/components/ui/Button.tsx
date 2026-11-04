import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface ButtonProps {
  children: ReactNode;
  /** primary: blue. dark: navy. light: white, for colored backgrounds. outline: white with a thin edge, for cards. */
  variant?: "primary" | "dark" | "light" | "outline" | "danger";
  size?: "md" | "sm";
  /** A path inside the app. Renders a router link. */
  to?: string;
  /** A full page address such as /auth/login. Renders a plain link. */
  href?: string;
  type?: "button" | "submit";
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  form?: string;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  to,
  href,
  type = "button",
  onClick,
  disabled,
  className = "",
  form,
  ...aria
}: ButtonProps) {
  const classes = `button button--${variant}${size === "sm" ? " button--sm" : ""} ${className}`.trim();
  if (to) {
    return (
      <Link className={classes} to={to} {...aria}>
        {children}
      </Link>
    );
  }
  if (href) {
    return (
      <a className={classes} href={href} {...aria}>
        {children}
      </a>
    );
  }
  return (
    <button className={classes} type={type} onClick={onClick} disabled={disabled} form={form} {...aria}>
      {children}
    </button>
  );
}
