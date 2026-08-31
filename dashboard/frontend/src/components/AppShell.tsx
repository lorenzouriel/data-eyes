import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

type NavId = "status" | "ask";

const THEME_KEY = "data-eyes-theme";

function initialTheme(): "light" | "dark" {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initials(name: string): string {
  return name
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

// Shared topbar + page frame for every Strata-design page — the design puts
// identical chrome (brand, nav, theme toggle, account menu) on every view,
// so it lives once here instead of being copy-pasted per page like the
// previous design's pages did.
export default function AppShell({ active, children }: { active: NavId; children: ReactNode }) {
  const { username, role, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const navItems: { id: NavId; label: string; path: string }[] = [
    { id: "status", label: "Status", path: "/" },
    { id: "ask", label: "Ask", path: "/ask" },
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand" onClick={() => navigate("/")}>
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Data Eyes</span>
        </div>
        <nav className="topbar-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`topbar-nav-btn ${active === item.id ? "active" : ""}`}
              onClick={() => navigate(item.path)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <button className="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "Dark" : "Light"}
          </button>
          <div className="account-menu">
            <button className="account-menu-trigger" onClick={() => setMenuOpen((v) => !v)}>
              <span className="account-avatar">{username ? initials(username) : "?"}</span>
              <span className="account-caret">▼</span>
            </button>
            {menuOpen && (
              <div className="account-dropdown">
                <div className="account-dropdown-header">
                  <span className="account-dropdown-name">{username}</span>
                  <span className="account-dropdown-email">{role === "admin" ? "Admin" : "Member"}</span>
                </div>
                {role === "admin" && (
                  <button
                    className="account-dropdown-item"
                    onClick={() => {
                      setMenuOpen(false);
                      navigate("/admin");
                    }}
                  >
                    Admin panel
                  </button>
                )}
                <button
                  className="account-dropdown-item"
                  onClick={() => {
                    setMenuOpen(false);
                    navigate("/account");
                  }}
                >
                  Account
                </button>
                <button
                  className="account-dropdown-item"
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
