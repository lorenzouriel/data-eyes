import type { JSX } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Login from "./pages/Login";
import FleetStatus from "./pages/FleetStatus";
import InstanceDetail from "./pages/InstanceDetail";
import Admin from "./pages/Admin";
import Ask from "./pages/Ask";
import Account from "./pages/Account";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { username, loading } = useAuth();
  if (loading) return <div className="page-loading">Loading…</div>;
  if (!username) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <FleetStatus />
              </ProtectedRoute>
            }
          />
          <Route
            path="/instances/:instanceName/:tab?"
            element={
              <ProtectedRoute>
                <InstanceDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/:tab?"
            element={
              <ProtectedRoute>
                <Admin />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ask"
            element={
              <ProtectedRoute>
                <Ask />
              </ProtectedRoute>
            }
          />
          <Route
            path="/account"
            element={
              <ProtectedRoute>
                <Account />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
