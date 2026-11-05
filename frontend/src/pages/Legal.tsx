import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { about as loadAbout } from "../api/public";
import type { About } from "../api/public";
import { LogoMark } from "../components/ui/LogoMark";

/** Change this date whenever the wording of either page changes. */
const UPDATED = "November 4, 2026";

function useAbout(): About {
  const [info, setInfo] = useState<About>({ org_name: "No More Under", contact_email: null, address: null, app_url: "" });
  useEffect(() => {
    loadAbout()
      .then(setInfo)
      .catch(() => undefined);
  }, []);
  return info;
}

/** "write to launches@... " when NMU has set a contact address, otherwise "ask the NMU admin who added you". */
function Contact({ info }: { info: About }) {
  if (info.contact_email) {
    return (
      <>
        email <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>
      </>
    );
  }
  return <>ask the NMU admin who added you, or reply to any email from NMU Launches</>;
}

function LegalPage({ title, intro, children, info }: { title: string; intro: ReactNode; children: ReactNode; info: About }) {
  useEffect(() => {
    document.title = `${title} · NMU Launches`;
    return () => {
      document.title = "NMU Launches";
    };
  }, [title]);

  return (
    <div className="legal">
      <header className="legal-top">
        <Link to="/" className="logo">
          <LogoMark size={32} />
          NMU Launches
        </Link>
        <nav aria-label="Policies" className="legal-nav">
          <Link to="/privacy" aria-current={title === "Privacy Policy" ? "page" : undefined}>
            Privacy
          </Link>
          <Link to="/terms" aria-current={title === "Terms of Use" ? "page" : undefined}>
            Terms
          </Link>
        </nav>
      </header>
      <main className="legal-body" id="main">
        <article className="legal-article">
          <h1>{title}</h1>
          <p className="legal-updated">Last updated {UPDATED}</p>
          <div className="legal-intro">{intro}</div>
          {children}
          <section aria-labelledby="who-runs-it">
            <h2 id="who-runs-it">Who runs NMU Launches</h2>
            <p>
              NMU Launches is run by {info.org_name}
              {info.address ? `, ${info.address}` : ""}. For any question about this page, or to make a request about your
              information, <Contact info={info} />.
            </p>
          </section>
        </article>
      </main>
    </div>
  );
}

export function PrivacyPolicy() {
  const info = useAbout();
  return (
    <LegalPage
      title="Privacy Policy"
      info={info}
      intro={
        <p>
          NMU Launches is the tool {info.org_name} (NMU) staff and invited partners use to plan new swim program sites. It is
          not open to the public. This page explains what information it keeps, why, who else handles it, and how to have it
          changed or deleted.
        </p>
      }
    >
      <section aria-labelledby="collect">
        <h2 id="collect">What we keep</h2>
        <h3>When you sign in with Google</h3>
        <p>
          Google tells us your email address, your first and last name, and that Google has checked the email address. We
          use these to recognize you and show your name to your team. We never see your Google password, and we do not keep
          the Google sign in token after you are signed in.
        </p>
        <h3>What admins and teammates add</h3>
        <ul>
          <li>Your name, email, access level and roles.</li>
          <li>The tasks you are given, their dates and status, and the notes and links people add to them.</li>
          <li>Reminders you set for yourself.</li>
          <li>
            For each site, the partner contact's name, email and phone number, and the shipping address, so the team can
            reach the site.
          </li>
          <li>A history of changes: who did what to which task, and when.</li>
          <li>A log of the emails the app sends: who they went to, when, and whether they were delivered.</li>
        </ul>
        <p>
          Please do not put sensitive personal information in notes, such as health details, or anything about swim program
          participants. NMU Launches is not built to hold that kind of information.
        </p>
      </section>

      <section aria-labelledby="use">
        <h2 id="use">How we use it</h2>
        <ul>
          <li>To show each person their tasks and each launch its plan.</li>
          <li>To send work emails: reminders before tasks are due, a Monday summary, new task notices, and a welcome email.</li>
          <li>To keep a record of what happened on each launch, so the team can learn from it.</li>
        </ul>
        <p>
          We do not sell your information, use it for advertising, or use it to train AI models. We do not send marketing
          emails.
        </p>
      </section>

      <section aria-labelledby="cookies">
        <h2 id="cookies">Cookies</h2>
        <p>
          NMU Launches uses one cookie, <code>nmu_session</code>, to keep you signed in. It lasts up to 7 days, or until you
          sign out. The app cannot work without it, so there is nothing to opt in to. There are no analytics, advertising or
          tracking cookies, and no tracking pixels in emails. Fonts are served by the app itself, so loading a page does not
          contact any other company.
        </p>
      </section>

      <section aria-labelledby="share">
        <h2 id="share">Who else handles it</h2>
        <p>Only these companies process information for NMU Launches, and only to run it:</p>
        <ul>
          <li>
            <strong>Airtable</strong> stores the data. Airtable is NMU's database.
          </li>
          <li>
            <strong>Google</strong> handles signing in, and sends the app's emails through Gmail.
          </li>
          <li>
            <strong>Railway</strong> hosts the app. Like any web host, it keeps short-lived server logs, which include IP
            addresses.
          </li>
        </ul>
        <p>
          Inside NMU Launches, NMU staff can see every launch. Partners see only the launches they have been added to, the
          tasks on them, and notes marked Shared. They never see internal notes or the change history.
        </p>
        <p>We will share information with others only if the law requires it.</p>
      </section>

      <section aria-labelledby="google">
        <h2 id="google">Google user data</h2>
        <p>
          NMU Launches' use and transfer of information received from Google APIs adheres to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements. For people who sign in, NMU Launches asks Google only for basic profile
          information (name and email). One NMU-owned account also allows the app to send email through Gmail. The app uses
          that permission only to send its own emails, and never reads anyone's mailbox.
        </p>
      </section>

      <section aria-labelledby="keep">
        <h2 id="keep">How long we keep it</h2>
        <p>
          Your account stays while you work with NMU. When you leave, an admin deactivates it so you can no longer sign in.
          Launch plans and their history are kept as NMU's records of past programs. You can ask for your personal details to
          be removed at any time (see below).
        </p>
      </section>

      <section aria-labelledby="rights">
        <h2 id="rights">Your choices</h2>
        <ul>
          <li>
            <strong>See or correct</strong> what NMU Launches holds about you. Your name, email and tasks are on your My Tasks
            page; anything else, ask.
          </li>
          <li>
            <strong>Delete</strong> your information. We will deactivate your account and remove your name and email from
            NMU Launches. Records of finished work stay, but no longer name you.
          </li>
          <li>
            <strong>Stop emails.</strong> Reply to any email from NMU Launches, or use your mail app's Unsubscribe button. If
            you still have work in the app, we will talk with you about who takes it over.
          </li>
        </ul>
        <p>
          To make any of these requests, <Contact info={info} />. We will answer within 30 days.
        </p>
      </section>

      <section aria-labelledby="security">
        <h2 id="security">Keeping it safe</h2>
        <p>
          Only people an admin has added can sign in, and only with Google. Every connection uses HTTPS. Each person sees only
          what their access level allows. No system is perfectly secure, but if we learn of a problem that affects your
          information, we will tell you.
        </p>
      </section>

      <section aria-labelledby="children">
        <h2 id="children">Children</h2>
        <p>NMU Launches is for adults who work with NMU. It is not meant for children and does not collect information about them.</p>
      </section>

      <section aria-labelledby="changes">
        <h2 id="changes">Changes to this policy</h2>
        <p>
          If we change this policy, we will update the date at the top. If the change is significant, we will tell people
          who use NMU Launches by email first.
        </p>
      </section>
    </LegalPage>
  );
}

export function Terms() {
  const info = useAbout();
  return (
    <LegalPage
      title="Terms of Use"
      info={info}
      intro={
        <p>
          These terms cover using NMU Launches, the tool {info.org_name} (NMU) uses to plan new swim program sites. By signing
          in, you agree to them. The <Link to="/privacy">Privacy Policy</Link> explains how information is handled.
        </p>
      }
    >
      <section aria-labelledby="who">
        <h2 id="who">Who can use it</h2>
        <p>
          NMU Launches is for NMU staff, volunteers and partners that an NMU admin has invited. It is free to use, and there
          are no fees, subscriptions or payments of any kind.
        </p>
      </section>

      <section aria-labelledby="account">
        <h2 id="account">Your account</h2>
        <ul>
          <li>Sign in only with your own Google account, and do not share access with anyone else.</li>
          <li>Tell an NMU admin straight away if you think someone else has used your account.</li>
          <li>NMU can change your access level or end your access, for example when you stop working on NMU programs.</li>
        </ul>
      </section>

      <section aria-labelledby="use">
        <h2 id="use">Using it well</h2>
        <ul>
          <li>Use NMU Launches for NMU work only.</li>
          <li>
            Do not add sensitive personal information, such as health details or information about swim program participants.
          </li>
          <li>Only add links and files you are allowed to share.</li>
          <li>Do not try to reach parts of the app or data that your access level does not include, or interfere with how it runs.</li>
        </ul>
      </section>

      <section aria-labelledby="content">
        <h2 id="content">What you add</h2>
        <p>
          Tasks, notes, links and plans you add are NMU's working records. NMU may keep, edit or remove them as part of running
          its programs.
        </p>
      </section>

      <section aria-labelledby="availability">
        <h2 id="availability">Availability</h2>
        <p>
          NMU works to keep NMU Launches running and accurate, but it is provided as it is, without any promise that it will
          always be available or free of mistakes. Check important dates with your team. To the extent the law allows, NMU is
          not responsible for losses caused by the app being unavailable or wrong.
        </p>
      </section>

      <section aria-labelledby="changes">
        <h2 id="changes">Changes</h2>
        <p>
          NMU may update these terms. The date at the top shows the latest version. If a change is significant, NMU will email
          the people who use NMU Launches first.
        </p>
      </section>
    </LegalPage>
  );
}
