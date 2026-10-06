import type { JSX } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "../features/auth/AuthContext";
import Login from "../features/auth/pages/Login";
import FleetStatus from "../features/fleet/pages/FleetStatus";
import InstanceDashboard from "../features/instances/pages/InstanceDashboard";
import Admin from "../features/administration/pages/Admin";
import Ask from "../features/insights/pages/Ask";
import Account from "../features/account/pages/Account";
import Notifications from "../features/notifications/pages/Notifications";
import Alerts from "../features/alerts/pages/Alerts";

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
          <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
          <Route path="/alerts/:tab?" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
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
                <InstanceDashboard />
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
