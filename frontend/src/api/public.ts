import { get } from "./client";

/** Who runs NMU Launches, from /api/public/about. Contact and address are blank until NMU sets them. */
export interface About {
  org_name: string;
  contact_email: string | null;
  address: string | null;
  app_url: string;
}

export const about = () => get<About>("/api/public/about");
