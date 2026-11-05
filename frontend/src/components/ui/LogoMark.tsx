/** The No More Under logo: two reaching hands over a wave, in a circle. */
export function LogoMark({ size }: { size: number }) {
  // The name always sits beside the logo, so screen readers skip the image.
  return <img className="logo-mark" src="/nmu-logo.jpg" width={size} height={size} alt="" />;
}
