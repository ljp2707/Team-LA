import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Navigate } from "react-router-dom";
import { seasonStats } from "../api/archive";
import type { SeasonStats } from "../api/archive";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { LogoMark } from "../components/ui/LogoMark";
import "../styles/home.css";

/** The dot grid on "Tasks done this week": one dot per task, up to this many. */
const DOT_COLUMNS = 12;
const DOT_COUNT = 36;

const BUBBLES = [
  { left: "46%", size: 16, delay: "0s" },
  { left: "52%", size: 10, delay: "3s" },
  { left: "58%", size: 22, delay: "6.5s" },
  { left: "22%", size: 12, delay: "4.5s" },
  { left: "78%", size: 14, delay: "8.5s" },
];

const PROGRAMS = ["Swim Safely", "Learn to Swim with YMCA", "Learn to Swim with City"];

/** Passes a stagger index to CSS as --i. */
const order = (i: number) => ({ "--i": i }) as CSSProperties;

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Counts up from 0 to the value once, easing out, after a short wait. */
function CountUp({ value, delay = 0 }: { value: number; delay?: number }) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? value : 0));
  useEffect(() => {
    if (prefersReducedMotion() || value === 0) {
      setShown(value);
      return;
    }
    const duration = Math.min(1200, 500 + value * 40);
    let frame = 0;
    let begin = 0;
    const tick = (now: number) => {
      if (!begin) begin = now + delay;
      const t = Math.min(1, Math.max(0, (now - begin) / duration));
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, delay]);
  return (
    <span className="stat-number">
      <span aria-hidden="true">{shown}</span>
      <span className="visually-hidden">{value}</span>
    </span>
  );
}

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

/** Bubbles let off when someone taps the ring. */
const SPLASH = [
  { x: -34, size: 10, delay: 0 },
  { x: -8, size: 14, delay: 60 },
  { x: 18, size: 8, delay: 120 },
  { x: 40, size: 12, delay: 30 },
];

function LifeRing() {
  const radius = 74;
  const stripe = (2 * Math.PI * radius) / 8; // Four coral stripes, four white gaps
  // Each tap gets a new key, which restarts the dip and the splash from the start.
  const [dunk, setDunk] = useState(0);
  return (
    <div className="life-ring" aria-hidden="true">
      <div
        key={dunk}
        className={`life-ring-float${dunk ? " is-dunked" : ""}`}
        onPointerDown={() => setDunk((n) => n + 1)}
      >
        <svg viewBox="0 0 200 200">
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
        {dunk > 0 &&
          SPLASH.map((b) => (
            <span
              key={b.x}
              className="splash"
              style={{ "--x": `${b.x}px`, width: b.size, height: b.size, animationDelay: `${b.delay}ms` } as CSSProperties}
            />
          ))}
      </div>
    </div>
  );
}

/** Season numbers from /api/public/season-stats. The cards are hidden if they do not load. */
function useSeasonStats(): SeasonStats | null {
  const [stats, setStats] = useState<SeasonStats | null>(null);
  useEffect(() => {
    seasonStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);
  return stats;
}

function SeasonCard({ stats }: { stats: SeasonStats }) {
  const toLaunch = stats.sites_to_launch;
  const launched = stats.sites_launched;
  return (
    <Card className="stat-card hero-card" style={order(0)}>
      <h2>{stats.year} season</h2>
      <div className="stat-row">
        <div>
          <CountUp value={toLaunch} delay={450} />
          <span className="stat-label">sites to launch</span>
        </div>
        <div>
          <CountUp value={launched} delay={550} />
          <span className="stat-label">launched so far</span>
        </div>
      </div>
      <div
        className="season-bar"
        role="img"
        aria-label={`${launched} of ${toLaunch} sites launched`}
      >
        {Array.from({ length: toLaunch }, (_, index) => (
          <span key={index} className={index < launched ? "is-done" : undefined} style={order(index)} />
        ))}
      </div>
    </Card>
  );
}

function TasksCard({ done }: { done: number }) {
  // One filled dot per finished task, and a pulsing dot for the next one, so the picture matches the number.
  const filled = Math.min(done, DOT_COUNT);
  const dotClass = (index: number) => (index < filled ? "is-done" : index === filled ? "is-pulsing" : undefined);
  return (
    <Card className="stat-card hero-card" style={order(1)}>
      <h2>Tasks done this week</h2>
      <div className="stat-row">
        <CountUp value={done} delay={650} />
      </div>
      <div className="dot-grid" aria-hidden="true">
        {Array.from({ length: DOT_COUNT }, (_, index) => (
          // A diagonal wave: each dot waits for its column plus its row
          <span
            key={index}
            className={dotClass(index)}
            style={order((index % DOT_COLUMNS) + Math.floor(index / DOT_COLUMNS) * 2)}
          />
        ))}
      </div>
    </Card>
  );
}

export function Home() {
  const { me } = useAuth();
  const howItWorks = useRef<HTMLDialogElement>(null);
  const help = useRef<HTMLDialogElement>(null);
  const stats = useSeasonStats();

  if (me) return <Navigate to={me.home} replace />;

  return (
    <div className="home">
      <main className="hero">
        <header className="hero-top">
          <div className="logo">
            <LogoMark size={36} />
            No More Under
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
              {["Every site", "launched", "on time."].map((line, i) => (
                <span key={line} className="hero-line">
                  <span style={order(i)}>{line}</span>
                </span>
              ))}
            </h1>
            <p className="hero-rise" style={order(3)}>
              No More Under's shared home for opening new swim programs.
            </p>
            <div className="hero-action hero-rise" style={order(4)}>
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
            </div>
          </div>
          {stats && (
            <div className="hero-stats">
              <SeasonCard stats={stats} />
              <TasksCard done={stats.tasks_done_this_week} />
            </div>
          )}
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
            <span className="hero-foot-legal">
              A No More Under tool
              <Link to="/privacy">Privacy</Link>
              <Link to="/terms">Terms</Link>
            </span>
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
          Sign in with the Google account your admin added. If you cannot get in, ask an admin to add you.
        </p>
        <form method="dialog">
          <Button type="submit">Close</Button>
        </form>
      </dialog>
    </div>
  );
}
