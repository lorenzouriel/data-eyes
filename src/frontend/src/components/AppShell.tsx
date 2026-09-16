import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { THEME_KEY, getInitialTheme } from "../theme";

type NavId = "status" | "ask";

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
  const [theme, setTheme] = useState<"light" | "dark">(getInitialTheme);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const navItems: { id: NavId; label: string; path: string }[] = [
    { id: "status", label: "Dashboard", path: "/" },
    { id: "ask", label: "Ask", path: "/ask" },
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand" onClick={() => navigate("/")}>
          <img className="brand-mark" src="/logo.svg" alt="" aria-hidden="true" />
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
          <button
            className="theme-toggle"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
            title={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
          >
            {theme === "light" ? (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
              </svg>
            )}
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
