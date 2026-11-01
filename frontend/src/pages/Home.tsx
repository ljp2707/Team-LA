import { useRef } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { LogoMark } from "../components/ui/LogoMark";
import "../styles/home.css";

// TODO: load these numbers from the API once projects are built.
const SEASON_YEAR = 2026;
const SITES_TO_LAUNCH = 13;
const SITES_LAUNCHED = 6;
const TASKS_DONE_THIS_WEEK = 31;

// One row per line of the dot grid: b = done, p = pulsing, - = empty.
const DOT_ROWS = ["bbbbbbbpbb--", "bbbbbb-bbb--", "bbbbb-bb-bp-"];

const BUBBLES = [
  { left: "46%", size: 16, delay: "0s" },
  { left: "52%", size: 10, delay: "3s" },
  { left: "58%", size: 22, delay: "6.5s" },
  { left: "22%", size: 12, delay: "4.5s" },
  { left: "78%", size: 14, delay: "8.5s" },
];

const PROGRAMS = ["Swim Safely", "Learn to Swim with YMCA", "Learn to Swim with City"];

/** Draws one wave. It repeats every 720 units, so scrolling by half loops cleanly. */
function Wave({ layer, height, swell }: { layer: string; height: number; swell: number }) {
  const path = `M0 ${swell} q180 ${-swell * 2} 360 0${" t360 0".repeat(7)} V${height} H0 Z`;
  return (
    <div className={`wave wave--${layer}`}>
      <svg viewBox={`0 0 2880 ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <path d={path} fill="currentColor" />
      </svg>
    </div>
  );
}

function LifeRing() {
  const radius = 74;
  const stripe = (2 * Math.PI * radius) / 8; // Four coral stripes, four white gaps
  return (
    <div className="life-ring">
      <svg viewBox="0 0 200 200" aria-hidden="true">
        <circle cx="100" cy="100" r="52" fill="#BDD8EC" />
        <circle cx="100" cy="100" r={radius} fill="none" stroke="#fff" strokeWidth="46" />
        <circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke="var(--ring-coral)"
          strokeWidth="46"
          strokeDasharray={`${stripe} ${stripe}`}
          strokeDashoffset={stripe / 2}
        />
        <circle cx="100" cy="100" r="97" fill="none" stroke="#B9CBD9" strokeWidth="1.5" />
        <circle cx="100" cy="100" r="51" fill="none" stroke="#B9CBD9" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

function SeasonCard() {
  return (
    <Card className="stat-card">
      <h2>{SEASON_YEAR} season</h2>
      <div className="stat-row">
        <div>
          <span className="stat-number">{SITES_TO_LAUNCH}</span>
          <span className="stat-label">sites to launch</span>
        </div>
        <div>
          <span className="stat-number">{SITES_LAUNCHED}</span>
          <span className="stat-label">launched so far</span>
        </div>
      </div>
      <div
        className="season-bar"
        role="img"
        aria-label={`${SITES_LAUNCHED} of ${SITES_TO_LAUNCH} sites launched`}
      >
        {Array.from({ length: SITES_TO_LAUNCH }, (_, index) => (
          <span key={index} className={index < SITES_LAUNCHED ? "is-done" : undefined} />
        ))}
      </div>
    </Card>
  );
}

function TasksCard() {
  const dotClass: Record<string, string | undefined> = { b: "is-done", p: "is-pulsing" };
  return (
    <Card className="stat-card">
      <h2>Tasks done this week</h2>
      <div className="stat-row">
        <span className="stat-number">{TASKS_DONE_THIS_WEEK}</span>
      </div>
      <div className="dot-grid" aria-hidden="true">
        {DOT_ROWS.join("")
          .split("")
          .map((dot, index) => (
            <span key={index} className={dotClass[dot]} />
          ))}
      </div>
    </Card>
  );
}

export function Home() {
  const { me } = useAuth();
  const howItWorks = useRef<HTMLDialogElement>(null);
  const help = useRef<HTMLDialogElement>(null);

  if (me) return <Navigate to={me.home} replace />;

  return (
    <div className="home">
      <main className="hero">
        <header className="hero-top">
          <div className="logo">
            <LogoMark size={36} />
            NMU Launches
          </div>
          <nav className="hero-links" aria-label="About">
            <button type="button" onClick={() => howItWorks.current?.showModal()}>
              How it works
            </button>
            <button type="button" onClick={() => help.current?.showModal()}>
              Help
            </button>
          </nav>
        </header>

        <div className="hero-body">
          <div className="hero-copy">
            <h1>
              Every site
              <br />
              launched
              <br />
              on time.
            </h1>
            <p>
              No More Under's shared home for opening new swim programs. Pick a template and
              a Day 1, and every task, owner and reminder is set up for you.
            </p>
            <div className="hero-action">
              <Button href="/auth/login" variant="dark">
                Sign in with Google
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M2 8h11M8.5 3.5 13 8l-4.5 4.5"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </Button>
              <span>Use your NMU Google account</span>
            </div>
          </div>
          <div className="hero-stats">
            <SeasonCard />
            <TasksCard />
          </div>
        </div>

        <LifeRing />

        <div className="water">
          <Wave layer="light" height={200} swell={14} />
          <Wave layer="mid" height={200} swell={18} />
          <Wave layer="deep" height={200} swell={30} />
          {BUBBLES.map((bubble) => (
            <span
              key={bubble.left}
              className="bubble"
              style={{
                left: bubble.left,
                width: bubble.size,
                height: bubble.size,
                animationDelay: bubble.delay,
              }}
            />
          ))}
          <footer className="hero-foot">
            <ul>
              {PROGRAMS.map((program) => (
                <li key={program}>{program}</li>
              ))}
            </ul>
            <span>A No More Under tool</span>
          </footer>
        </div>
      </main>

      <dialog ref={howItWorks} className="home-dialog" aria-labelledby="how-it-works-title">
        <h2 id="how-it-works-title">How it works</h2>
        <ol>
          <li>An admin picks a template and a Day 1 for a new site.</li>
          <li>Every task is created with a due date and an owner.</li>
          <li>Each person sees their own tasks and gets a reminder before they are due.</li>
        </ol>
        <form method="dialog">
          <Button type="submit">Close</Button>
        </form>
      </dialog>

      <dialog ref={help} className="home-dialog" aria-labelledby="help-title">
        <h2 id="help-title">Help</h2>
        <p>
          Sign in with your NMU Google account. If you cannot get in, ask an admin to add you.
        </p>
        <form method="dialog">
          <Button type="submit">Close</Button>
        </form>
      </dialog>
    </div>
  );
}
